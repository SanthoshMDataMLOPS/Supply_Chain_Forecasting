"""Compile, submit and schedule the Vertex AI pipelines.

    python run_pipeline.py compile  --image IMG --out compiled_pipelines
    python run_pipeline.py submit   --pipeline training  --project P --region R --bucket B --sa SA
    python run_pipeline.py schedule --pipeline inference --cron "0 6 * * *" ...   # idempotent
"""

from __future__ import annotations

import argparse
import os
import sys


def _compile(image: str, out: str) -> dict[str, str]:
    os.environ["PIPELINE_IMAGE"] = image  # read by components.py at import time
    from kfp import compiler

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from pipelines.inference_pipeline import inference_pipeline
    from pipelines.training_pipeline import training_pipeline

    os.makedirs(out, exist_ok=True)
    paths = {}
    for name, fn in {"training": training_pipeline, "inference": inference_pipeline}.items():
        path = os.path.join(out, f"{name}_pipeline.json")
        compiler.Compiler().compile(pipeline_func=fn, package_path=path)
        paths[name] = path
        print("compiled", path)
    return paths


def _job(args, template: str):
    from google.cloud import aiplatform

    aiplatform.init(project=args.project, location=args.region, staging_bucket=f"gs://{args.bucket}")
    return aiplatform.PipelineJob(
        display_name=f"inbound-container-{args.pipeline}",
        template_path=template,
        pipeline_root=f"gs://{args.bucket}/pipeline_root/{args.pipeline}",
        parameter_values={"project_id": args.project, "region": args.region},
        enable_caching=False,
        labels={"use_case": "inbound-container-volume", "stage": args.env},
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["compile", "submit", "schedule"])
    p.add_argument("--image", default=os.environ.get("PIPELINE_IMAGE", ""))
    p.add_argument("--out", default="compiled_pipelines")
    p.add_argument("--pipeline", choices=["training", "inference"])
    p.add_argument("--project")
    p.add_argument("--region", default="us-central1")
    p.add_argument("--bucket")
    p.add_argument("--sa", help="pipeline runner service account")
    p.add_argument("--cron", help="e.g. '0 6 * * *' (UTC)")
    p.add_argument("--env", default="dev")
    args = p.parse_args()

    paths = _compile(args.image, args.out)
    if args.command == "compile":
        return

    job = _job(args, paths[args.pipeline])
    if args.command == "submit":
        job.submit(service_account=args.sa)
        print("submitted:", job.resource_name)
        return

    # schedule: replace any existing schedule with the same display name
    from google.cloud import aiplatform

    name = f"inbound-container-{args.pipeline}-{args.env}"
    for old in aiplatform.PipelineJobSchedule.list(filter=f'display_name="{name}"'):
        old.delete()
    schedule = job.create_schedule(
        display_name=name, cron=f"TZ=UTC {args.cron}", service_account=args.sa, max_concurrent_run_count=1
    )
    print("scheduled:", schedule.resource_name)


if __name__ == "__main__":
    main()
