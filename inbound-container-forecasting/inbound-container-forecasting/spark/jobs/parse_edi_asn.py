"""Flatten nested EDI 856 (Advance Ship Notice) payloads into one row per container.

Runs on Dataproc Serverless for Spark. The raw ASN JSON is deeply nested
(shipment -> orders -> containers -> items), which is awkward to unnest in SQL
at volume, so this is the one step that lives in Spark (the "complex data" box
in the architecture diagram).

    gcloud dataproc batches submit pyspark spark/jobs/parse_edi_asn.py \
        --region=us-central1 --version=2.2 \
        --deps-bucket=gs://$PROJECT-dataproc-deps \
        --subnet=default \
        -- --input=gs://$PROJECT-landing/edi856/dt=2026-01-01/*.json \
           --output-table=$PROJECT.logistics_raw.parsed_edi_asn \
           --temp-bucket=$PROJECT-dataproc-temp
"""

from __future__ import annotations

import argparse

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T

CONTAINER_SCHEMA = T.StructType(
    [
        T.StructField("container_id", T.StringType()),
        T.StructField("teu", T.DoubleType()),
        T.StructField("seal_no", T.StringType()),
    ]
)

ASN_SCHEMA = T.StructType(
    [
        T.StructField("asn_id", T.StringType()),
        T.StructField("asn_revision", T.IntegerType()),
        T.StructField("carrier_scac", T.StringType()),
        T.StructField("ship_to_dc", T.StringType()),
        T.StructField("eta", T.StringType()),
        T.StructField("origin_port", T.StringType()),
        T.StructField("containers", T.ArrayType(CONTAINER_SCHEMA)),
    ]
)


def flatten_asn(raw: DataFrame) -> DataFrame:
    """Explode containers and normalise types. Pure function so it can be unit tested."""
    return (
        raw.withColumn("container", F.explode_outer("containers"))
        .select(
            F.col("container.container_id").alias("container_id"),
            F.upper(F.trim("ship_to_dc")).alias("dc_id"),
            F.to_timestamp("eta").alias("eta_ts"),
            F.col("container.teu").alias("teu"),
            "asn_id",
            "asn_revision",
            "carrier_scac",
            "origin_port",
        )
        .where(F.col("container_id").isNotNull() & F.col("eta_ts").isNotNull())
        .withColumn("ingested_at", F.current_timestamp())
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output-table", required=True, help="project.dataset.table")
    p.add_argument("--temp-bucket", required=True)
    args = p.parse_args()

    spark = SparkSession.builder.appName("parse-edi-asn").getOrCreate()
    raw = spark.read.schema(ASN_SCHEMA).json(args.input)
    flat = flatten_asn(raw)

    (
        flat.write.format("bigquery")
        .option("table", args.output_table)
        .option("temporaryGcsBucket", args.temp_bucket)
        .option("partitionField", "eta_ts")
        .option("partitionType", "DAY")
        .mode("append")
        .save()
    )


if __name__ == "__main__":
    main()
