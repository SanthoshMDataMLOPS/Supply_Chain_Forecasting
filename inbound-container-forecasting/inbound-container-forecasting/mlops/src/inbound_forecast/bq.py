"""Thin BigQuery helpers. Imports are lazy so unit tests do not need GCP libraries."""

from __future__ import annotations

import pandas as pd


def read_sql(project_id: str, sql: str, location: str = "US") -> pd.DataFrame:
    from google.cloud import bigquery

    client = bigquery.Client(project=project_id, location=location)
    return client.query(sql).to_dataframe(create_bqstorage_client=True)


def write_df(
    project_id: str,
    df: pd.DataFrame,
    table: str,
    write_disposition: str = "WRITE_APPEND",
    location: str = "US",
) -> None:
    from google.cloud import bigquery

    client = bigquery.Client(project=project_id, location=location)
    job = client.load_table_from_dataframe(
        df,
        f"{project_id}.{table}",
        job_config=bigquery.LoadJobConfig(write_disposition=write_disposition),
    )
    job.result()


def feature_query(project_id: str, table: str) -> str:
    return f"SELECT * FROM `{project_id}.{table}`"
