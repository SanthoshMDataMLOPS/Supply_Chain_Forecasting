.PHONY: install lint test compile-dataform compile-pipelines local-demo docker-build tf-validate

PROJECT_ID ?= $(shell gcloud config get-value project 2>/dev/null)
REGION     ?= us-central1
IMAGE      ?= $(REGION)-docker.pkg.dev/$(PROJECT_ID)/mlops/inbound-forecast:dev

install:
	pip install -e "mlops/[dev]"

lint:
	ruff check mlops tests spark
	ruff format --check mlops tests spark

test:
	pytest tests -q

compile-dataform:
	cd dataform && npx --yes @dataform/cli@3 compile

compile-pipelines:
	PYTHONPATH=mlops/src:mlops python mlops/pipelines/run_pipeline.py compile --image $(IMAGE) --out compiled_pipelines

local-demo:
	PYTHONPATH=mlops/src python mlops/scripts/local_demo.py

docker-build:
	docker build -f mlops/Dockerfile -t $(IMAGE) mlops

tf-validate:
	cd infra/terraform && terraform init -backend=false && terraform validate
