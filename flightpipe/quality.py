"""Twelve automated data-quality checks on the loaded data.

Each check counts violations. An "error" check with any violation fails the run (exit
code 2), so a bad file never reaches the reports. A "warn" check is reported, not fatal.
Results are kept in the `dq_results` table, one row per check per run.
"""
import logging
import sqlite3

import pandas as pd

from .config import CAUSE_COLS

log = logging.getLogger("flightpipe.quality")

OPERATED = "CANCELLED = 0 AND DIVERTED = 0"
CAUSE_SUM = " + ".join(f"COALESCE({c}, 0)" for c in CAUSE_COLS)

# (id, description, severity, SQL returning the number of violations)
SQL_CHECKS = [
    ("DQ-02", "Every row the manifest says was inserted is in the table", "error",
     "SELECT ABS((SELECT COUNT(*) FROM flights) - (SELECT COALESCE(SUM(rows_inserted), 0) FROM load_manifest))"),
    ("DQ-04", "Key fields are never blank (date, carrier, origin, destination, schedule, status)", "error",
     "SELECT COUNT(*) FROM flights WHERE FL_DATE IS NULL OR OP_UNIQUE_CARRIER IS NULL OR ORIGIN IS NULL "
     "OR DEST IS NULL OR CRS_DEP_TIME IS NULL OR CRS_ARR_TIME IS NULL OR CANCELLED IS NULL OR DIVERTED IS NULL"),
    ("DQ-05", "Carrier codes exist in the BTS carrier lookup", "error",
     "SELECT COUNT(DISTINCT OP_UNIQUE_CARRIER) FROM flights WHERE OP_UNIQUE_CARRIER NOT IN (SELECT Code FROM lkp_carriers)"),
    ("DQ-06", "Origin and destination codes exist in the BTS airport lookup", "error",
     "SELECT (SELECT COUNT(DISTINCT ORIGIN) FROM flights WHERE ORIGIN NOT IN (SELECT Code FROM lkp_airports)) + "
     "(SELECT COUNT(DISTINCT DEST) FROM flights WHERE DEST NOT IN (SELECT Code FROM lkp_airports))"),
    ("DQ-07", "Cancelled flights have a valid reason code, and other flights have none", "error",
     "SELECT COUNT(*) FROM flights WHERE (CANCELLED = 1 AND (CANCELLATION_CODE IS NULL OR CANCELLATION_CODE "
     "NOT IN (SELECT Code FROM lkp_cancellation))) OR (CANCELLED = 0 AND CANCELLATION_CODE IS NOT NULL)"),
    ("DQ-08", "Cancelled flights have no arrival time or arrival delay", "error",
     "SELECT COUNT(*) FROM flights WHERE CANCELLED = 1 AND (ARR_TIME IS NOT NULL OR ARR_DELAY IS NOT NULL)"),
    ("DQ-09", "Operated flights have an arrival delay", "error",
     f"SELECT COUNT(*) FROM flights WHERE {OPERATED} AND ARR_DELAY IS NULL"),
    ("DQ-10", "The 15-minute flag agrees with the arrival delay", "error",
     f"SELECT COUNT(*) FROM flights WHERE {OPERATED} AND ARR_DEL15 <> (CASE WHEN ARR_DELAY >= 15 THEN 1 ELSE 0 END)"),
    ("DQ-11", "Scheduled times are valid hhmm clock times", "error",
     "SELECT COUNT(*) FROM flights WHERE CRS_DEP_TIME % 100 > 59 OR CRS_DEP_TIME > 2400 OR CRS_DEP_TIME < 0 "
     "OR CRS_ARR_TIME % 100 > 59 OR CRS_ARR_TIME > 2400 OR CRS_ARR_TIME < 0"),
    ("DQ-12", "Delay-cause minutes add up to the arrival delay (flights 15+ min late)", "warn",
     f"SELECT COUNT(*) FROM flights WHERE {OPERATED} AND ARR_DELAY >= 15 AND ({CAUSE_SUM}) <> ARR_DELAY"),
]


def run(cfg, run_id, load_result):
    con = sqlite3.connect(cfg["paths"]["database"])
    year = cfg["load"]["year"]
    manifest = pd.read_sql("SELECT * FROM load_manifest", con)
    bad_period = int(sum(1 for p in manifest.periods
                         if len(p.split(";")) != 1 or not p.startswith(f"{year}-")))
    rows = [
        ("DQ-01", "Every monthly file has the columns the pipeline needs", "error",
         len(load_result.get("schema_problems", []))),
        ("DQ-03", f"Each file holds exactly one month of {year}", "error", bad_period),
    ]
    for cid, desc, sev, sql in SQL_CHECKS:
        rows.append((cid, desc, sev, int(con.execute(sql).fetchone()[0])))
    out = pd.DataFrame(rows, columns=["check_id", "description", "severity", "violations"])
    out = out.sort_values("check_id").reset_index(drop=True)
    out["status"] = ["pass" if v == 0 else ("fail" if s == "error" else "warn")
                     for v, s in zip(out.violations, out.severity)]
    out.insert(0, "run_id", run_id)
    out.to_sql("dq_results", con, if_exists="append", index=False)
    con.close()
    for r in out.itertuples():
        level = logging.ERROR if r.status == "fail" else logging.WARNING if r.status == "warn" else logging.INFO
        log.log(level, "%s %s: %s violations (%s)", r.check_id, r.status.upper(), f"{r.violations:,}", r.description)
    return out
