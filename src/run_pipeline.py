"""Run the whole pipeline: ingest -> validate -> analyse -> data-quality report.

    python src/run_pipeline.py            # full run (about 3 minutes)
    python src/run_pipeline.py --skip-ingest   # reuse data/flights.db
"""
import sys
import time
from datetime import date

import analyze
import ingest
import validate
from config import DB_PATH, REPORT_PATH


def write_report(file_log, dupes, checks, val):
    lines = [f"# Data quality report", "", f"Generated {date.today().isoformat()}.", "",
             "## Files loaded", "", "| File | Rows read | Rows loaded |", "|---|---:|---:|"]
    for f in file_log:
        lines.append(f"| {f['file']} | {f['rows_read']:,} | {f['rows_loaded']:,} |")
    lines += ["", f"Exact duplicate rows removed: **{dupes}**", "",
              "## Checks on the loaded table", "", "| Check | Result | Expected |", "|---|---:|---|"]
    for name, value, expect in checks:
        lines.append(f"| {name} | {value:,} | {expect} |")
    ok, n = int(val.match.sum()), len(val)
    n_tot = int((val.carrier_name == "ALL CARRIERS").sum())
    lines += ["", "## Validation against published DOT figures", "",
              f"**{ok} of {n}** published on-time rates ({n - n_tot} carrier-months and "
              f"{n_tot} monthly all-carrier totals) match Table 1A of the DOT Air Travel Consumer Report within the ±0.05-point "
              "rounding band. Full comparison: `outputs/tables/validation_vs_dot_atcr.csv`.", ""]
    worst = val.reindex(val.difference_pts.abs().sort_values(ascending=False).index).head(5)
    lines += ["Largest differences:", "", "| Month | Carrier | Published | Computed | Diff |",
              "|---:|---|---:|---:|---:|"]
    for _, r in worst.iterrows():
        lines.append(f"| {r.month} | {r.carrier_name} | {r.published_on_time_pct:.1f} | "
                     f"{r.computed_on_time_pct:.3f} | {r.difference_pts:+.3f} |")
    REPORT_PATH.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    t0 = time.time()
    if "--skip-ingest" in sys.argv and DB_PATH.exists():
        file_log, dupes, checks = None, None, None
        print("Skipping ingest; using existing database.")
    else:
        print("1/3 Ingesting raw files into SQLite ...")
        file_log, dupes, checks = ingest.run()
    print("2/3 Validating against DOT published figures ...")
    val = validate.run()
    print("3/3 Running analyses ...")
    analyze.run()
    if file_log is not None:
        write_report(file_log, dupes, checks, val)
        print(f"Data-quality report written to {REPORT_PATH.relative_to(REPORT_PATH.parents[1])}")
    print(f"Done in {time.time() - t0:.0f}s.")
