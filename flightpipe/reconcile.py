"""Recompute every published carrier-month on-time rate and compare it with DOT's figure."""
import logging
import sqlite3

import pandas as pd

from . import reference

log = logging.getLogger("flightpipe.reconcile")

SQL = """
SELECT YEAR AS year, MONTH AS month, OP_UNIQUE_CARRIER AS carrier,
       COUNT(*) AS scheduled_flights, SUM(ON_TIME) AS on_time_flights
FROM flights GROUP BY YEAR, MONTH, OP_UNIQUE_CARRIER
"""


def run(cfg, run_id):
    tol = cfg["reconcile"]["tolerance_pts"]
    con = sqlite3.connect(cfg["paths"]["database"])
    ref = reference.build(cfg)
    ref.to_sql("published_figures", con, if_exists="replace", index=False)
    by = pd.read_sql(SQL, con)
    by["carrier_name"] = by.carrier.map(cfg["carriers"])
    unmapped = sorted(set(by.carrier[by.carrier_name.isna()]))
    if unmapped:
        log.warning("carriers without an ATCR name in pipeline.toml: %s", unmapped)
    total = by.groupby(["year", "month"], as_index=False)[["scheduled_flights", "on_time_flights"]].sum()
    total["carrier"], total["carrier_name"] = "ALL", "ALL CARRIERS"
    comp = pd.concat([by, total], ignore_index=True)
    comp["computed_on_time_pct"] = 100 * comp.on_time_flights / comp.scheduled_flights
    out = ref.merge(comp, on=["year", "month", "carrier_name"], how="left")
    out["difference_pts"] = (out.computed_on_time_pct - out.published_on_time_pct).round(4)
    out["match"] = out.difference_pts.abs() <= tol + 1e-9
    out["computed_on_time_pct"] = out.computed_on_time_pct.round(4)
    out = out[["year", "month", "carrier", "carrier_name", "scheduled_flights", "published_on_time_pct",
               "computed_on_time_pct", "difference_pts", "match", "source_report", "source_table", "method"]]
    out.insert(0, "run_id", run_id)
    out.to_sql("reconciliation", con, if_exists="append", index=False)
    con.close()
    outdir = cfg["paths"]["outputs"]
    outdir.mkdir(parents=True, exist_ok=True)
    out.drop(columns="run_id").to_csv(outdir / "reconciliation_vs_dot.csv", index=False)
    ok = int(out.match.sum())
    (log.info if ok == len(out) else log.error)(
        "reconciliation: %d of %d published figures reproduced within +/-%.2f points", ok, len(out), tol)
    return out
