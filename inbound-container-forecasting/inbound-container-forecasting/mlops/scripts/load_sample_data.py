"""Create synthetic RAW tables in BigQuery so the whole pipeline can be exercised end to end
(Dataform -> Vertex AI) in a fresh GCP project without any real logistics data.

    python mlops/scripts/load_sample_data.py --project my-project --dry-run   # just build + print
    python mlops/scripts/load_sample_data.py --project my-project              # load into BigQuery

Creates: logistics_raw.inbound_container_events, logistics_raw.parsed_edi_asn,
         logistics_raw.dock_appointments, inventory_raw.inventory_snapshots
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from inbound_forecast.synthetic import generate_daily  # noqa: E402

HORIZON = 14


def build_raw_tables(n_dcs: int = 5, days: int = 730, seed: int = 11) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    daily = generate_daily(n_dcs=n_dcs, days=days + HORIZON, seed=seed, end=str(pd.Timestamp.today().date() + pd.Timedelta(days=HORIZON)))
    today = pd.Timestamp.today().normalize()

    events, asn, dock, inv = [], [], [], []
    cid = 0
    carriers = ["MAEU", "MSCU", "CMDU", "HLCU", "ONEY"]
    ports = ["CNSHA", "CNNGB", "VNSGN", "INMUN", "USLAX"]
    for r in daily.itertuples():
        d = pd.Timestamp(r.arrival_date)
        n_plan = int(r.planned_containers)
        # ASN rows exist for past and future ETAs
        for _ in range(n_plan):
            cid += 1
            eta = d + pd.Timedelta(hours=float(rng.uniform(0, 23)))
            asn.append((f"CONT{cid:09d}", r.dc_id, eta, 1.6, 1, str(rng.choice(carriers)), str(rng.choice(ports)),
                        f"ASN{cid:09d}", pd.Timestamp.now("UTC")))
        if d <= today:  # actual gate events only for the past
            for _ in range(int(r.container_count)):
                cid += 1
                gate_in = d + pd.Timedelta(hours=float(rng.uniform(0, 23)))
                dwell = max(0.3, float(rng.normal(r.avg_dwell_days, 0.8)))
                cn = f"CONT{cid:09d}"
                events.append((cn, r.dc_id, "GATE_IN", gate_in, 1.6, str(rng.choice(carriers)), str(rng.choice(ports))))
                out = gate_in + pd.Timedelta(days=dwell)
                if out <= pd.Timestamp.now("UTC").tz_localize(None):
                    events.append((cn, r.dc_id, "GATE_OUT", out, 1.6, None, None))
            n_appt = int(r.container_count * rng.uniform(0.95, 1.05))
            for _ in range(n_appt):
                dock.append((r.dc_id, d + pd.Timedelta(hours=float(rng.uniform(6, 20))), "COMPLETED"))
            inv.append((r.dc_id, d.date(), float(r.inventory_utilization * 1_000_000), float(r.on_order_units), 1_000_000.0))

    return {
        "logistics_raw.inbound_container_events": pd.DataFrame(
            events, columns=["container_id", "dc_id", "event_type", "event_ts", "teu", "carrier_scac", "origin_port"]),
        "logistics_raw.parsed_edi_asn": pd.DataFrame(
            asn, columns=["container_id", "dc_id", "eta_ts", "teu", "asn_revision", "carrier_scac", "origin_port", "asn_id", "ingested_at"]),
        "logistics_raw.dock_appointments": pd.DataFrame(dock, columns=["dc_id", "appointment_ts", "status"]),
        "inventory_raw.inventory_snapshots": pd.DataFrame(
            inv, columns=["dc_id", "snapshot_date", "on_hand_units", "on_order_units", "storage_capacity_units"]),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--project", required=True)
    p.add_argument("--location", default="US")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    tables = build_raw_tables()
    for name, df in tables.items():
        print(f"{name}: {len(df):,} rows")
    if args.dry_run:
        return

    from google.cloud import bigquery

    client = bigquery.Client(project=args.project, location=args.location)
    for name, df in tables.items():
        client.load_table_from_dataframe(
            df, f"{args.project}.{name}",
            job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE"),
        ).result()
        print("loaded", name)


if __name__ == "__main__":
    main()
