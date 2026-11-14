import pytest

pyspark = pytest.importorskip("pyspark")


def test_flatten_asn_explodes_containers():
    from pyspark.sql import SparkSession

    from spark.jobs.parse_edi_asn import ASN_SCHEMA, flatten_asn

    spark = SparkSession.builder.master("local[1]").appName("t").getOrCreate()
    raw = spark.createDataFrame(
        [("A1", 2, "MAEU", " dc01 ", "2026-02-01T08:00:00", "CNSHA",
          [("C1", 2.0, "s1"), ("C2", 1.0, "s2"), (None, 1.0, "s3")])],
        schema=ASN_SCHEMA,
    )
    out = flatten_asn(raw).collect()
    assert {r.container_id for r in out} == {"C1", "C2"}
    assert all(r.dc_id == "DC01" for r in out)
