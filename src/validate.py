"""Step 2: check the pipeline against DOT's published on-time figures.

Recomputes the on-time percentage for every carrier and month, plus the
all-carrier total, and compares it with Table 1A of the Air Travel Consumer
Report (reference/atcr_table1a_ontime.csv). DOT prints one decimal place, so a
match means the difference is within the 0.05-point rounding band.
"""
import sqlite3

import pandas as pd

from config import DB_PATH, REFERENCE_DIR, TABLES_DIR

TOLERANCE = 0.05


def run():
    con = sqlite3.connect(DB_PATH)
    by_carrier = pd.read_sql("""
        SELECT f.MONTH AS month, c.atcr_name AS carrier_name,
               COUNT(*) AS scheduled_flights,
               100.0 * SUM(f.ON_TIME) / COUNT(*) AS computed_on_time_pct
        FROM flights f JOIN carriers c ON c.code = f.OP_UNIQUE_CARRIER
        GROUP BY f.MONTH, c.atcr_name""", con)
    total = pd.read_sql("""
        SELECT MONTH AS month, 'ALL CARRIERS' AS carrier_name,
               COUNT(*) AS scheduled_flights,
               100.0 * SUM(ON_TIME) / COUNT(*) AS computed_on_time_pct
        FROM flights GROUP BY MONTH""", con)
    con.close()

    computed = pd.concat([by_carrier, total], ignore_index=True)
    ref = pd.read_csv(REFERENCE_DIR / "atcr_table1a_ontime.csv")
    out = ref.merge(computed, on=["month", "carrier_name"], how="left")
    out["computed_on_time_pct"] = out.computed_on_time_pct.round(3)
    out["difference_pts"] = (out.computed_on_time_pct - out.published_on_time_pct).round(3)
    out["match"] = out.difference_pts.abs() <= TOLERANCE
    out = out[["month", "carrier_name", "scheduled_flights", "published_on_time_pct",
               "computed_on_time_pct", "difference_pts", "match", "source_report"]]
    out.to_csv(TABLES_DIR / "validation_vs_dot_atcr.csv", index=False)
    n, ok = len(out), int(out.match.sum())
    print(f"  validation: {ok}/{n} carrier-month figures match DOT within ±{TOLERANCE} pts")
    return out


if __name__ == "__main__":
    run()
