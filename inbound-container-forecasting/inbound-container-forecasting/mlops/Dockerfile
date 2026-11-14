# Base image for every Vertex AI pipeline component (training + inference).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install ".[pipelines]"

# KFP components are executed by the KFP launcher, no ENTRYPOINT needed.
