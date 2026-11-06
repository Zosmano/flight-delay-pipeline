"""Write the run report (Markdown) and a machine-readable run record (JSON)."""
import json
import sqlite3
from datetime import datetime, timezone

import pandas as pd


def fmt_ci(ci):
    return f"{ci[0]:+.1f} to {ci[1]:+.1f}"


def write(cfg, run_id, started, load_result, dq, rec, par, status):
    out = cfg["paths"]["outputs"]
    out.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(cfg["paths"]["database"])
    manifest = pd.read_sql("SELECT * FROM load_manifest ORDER BY periods", con)
    total = con.execute("SELECT COUNT(*) FROM flights").fetchone()[0]
    con.close()
    L = [f"# Run report: {run_id}", "",
         f"Status: **{status}**. Started {started:%Y-%m-%d %H:%M} UTC, "
         f"{(datetime.now(timezone.utc) - started).total_seconds():.0f} seconds.", "",
         "## 1. Load", "",
         f"{total:,} flight records in `{cfg['paths']['database'].name}` from {len(manifest)} monthly files.", "",
         "| File | Period | Rows inserted | Duplicates skipped | This run |", "|---|---|---:|---:|---|"]
    action = {f["file"]: f["action"] for f in load_result["files"]}
    for r in manifest.itertuples():
        L.append(f"| {r.file} | {r.periods} | {r.rows_inserted:,} | {r.duplicates:,} | {action.get(r.file, 'not seen')} |")
    flagged = dq[dq.status == "flagged"]
    L += ["", "## 2. Data-quality checks", "",
          f"All {len(dq)} checks ran: {(dq.status == 'pass').sum()} found no problems, "
          f"{(dq.status == 'fail').sum()} stopped the run and {len(flagged)} flagged rows for review."]
    if len(flagged):
        exc = pd.read_csv(out / "dq_exceptions.csv")
        for r in flagged.itertuples():
            e = exc[exc.check_id == r.check_id]
            L += ["", f"{r.check_id} flagged {r.violations:,} flights: " +
                  "; ".join(f"{n:,} where {k}" for k, n in e.finding.value_counts().items()) +
                  f" (carriers: {', '.join(f'{c} {n}' for c, n in e.OP_UNIQUE_CARRIER.value_counts().items())}). "
                  "These come from the BTS source files. The flights are valid for on-time reporting, so they "
                  "are kept, and each one is listed in `dq_exceptions.csv`."]
    L += ["", "| Check | What it tests | If it finds a problem | Result |", "|---|---|---|---|"]
    effect = {"blocking": "stops the run", "flag": "lists the rows; run continues"}
    for r in dq.itertuples():
        res = "pass" if r.status == "pass" else f"{r.violations:,} rows {'flagged' if r.status == 'flagged' else 'failed'}"
        L.append(f"| {r.check_id} | {r.description} | {effect[r.severity]} | {res} |")
    if rec is not None:
        n, ok = len(rec), int(rec.match.sum())
        man = int((rec.method == "manual").sum())
        L += ["", "## 3. Reconciliation with DOT's published figures", "",
              f"**{ok} of {n}** published on-time rates reproduced within "
              f"+/-{cfg['reconcile']['tolerance_pts']} points ({n - int((rec.carrier_name == 'ALL CARRIERS').sum())} "
              f"carrier-months and {int((rec.carrier_name == 'ALL CARRIERS').sum())} monthly all-carrier totals). "
              f"{n - man} published figures were extracted from the ATCR PDFs automatically; {man} were typed in "
              "from a report not on file (`reference/manual_reference.csv`).", "",
              "Largest differences:", "", "| Month | Carrier | Published | Computed | Difference | Source |",
              "|---:|---|---:|---:|---:|---|"]
        worst = rec.reindex(rec.difference_pts.abs().sort_values(ascending=False).index).head(5)
        for r in worst.itertuples():
            L.append(f"| {r.month} | {r.carrier_name} | {r.published_on_time_pct:.1f} | "
                     f"{r.computed_on_time_pct:.3f} | {r.difference_pts:+.3f} | {r.source_table} |")
    if par is not None:
        res, s, ap = par["result"], par["strata"], par["by_airport"]
        A, B = res["carrier_a"], res["carrier_b"]
        a, b = cfg["paradox"]["carrier_a"], cfg["paradox"]["carrier_b"]
        cr, st = res["crude_diff_pts"], res["stratified_diff_pts"]
        L += ["", f"## 4. Simpson's paradox: {A} vs {B}, arrivals at {', '.join(res['airports'])}", "",
              f"Pooled across the airports, {A} is on time {res['pooled_rate_pct'][A]:.1f}% of the time "
              f"({res['flights'][A]:,} flights) and {B} {res['pooled_rate_pct'][B]:.1f}% ({res['flights'][B]:,}). "
              f"{A} led in {len(res['months_a_led_pooled'])} of 7 months on the pooled figures.", "",
              "| Comparison | {A} minus {B} (points) | 95% CI, flights independent | 95% CI, resampling days |".format(A=A, B=B),
              "|---|---:|---|---|",
              f"| Pooled (crude) | {cr['estimate']:+.1f} | {fmt_ci(cr['ci_wald'])} | {fmt_ci(cr['ci_day_bootstrap'])} |",
              f"| Same airport and month ({res['strata_used']} groups) | {st['estimate']:+.1f} | {fmt_ci(st['ci_wald'])} | "
              f"{fmt_ci(st['ci_day_bootstrap'])} |", "",
              f"{A} is ahead in {res['strata_where_a_leads']} of {res['strata_used']} airport-by-month groups "
              f"(significantly in {res['strata_where_a_leads_significantly']}); {B} is significantly ahead in "
              f"{res['strata_where_b_leads_significantly']}. Paradox detected: **{'yes' if res['paradox'] else 'no'}**.", "",
              "Why the pooled figure reverses:", "",
              f"| Airport | {A} on time | {B} on time | Share of {A} flights | Share of {B} flights | Gap, same month |",
              "|---|---:|---:|---:|---:|---|"]
        for r in ap.itertuples():
            d = r._asdict()
            L.append(f"| {r.airport} | {d[f'rate_{a}_pct']:.1f}% | {d[f'rate_{b}_pct']:.1f}% | "
                     f"{r.share_of_a_flights:.0%} | {r.share_of_b_flights:.0%} | "
                     f"{r.stratified_diff_pts:+.1f} ({r.ci_low:+.1f} to {r.ci_high:+.1f}) |")
        L += ["", "![Pooled vs stratified](paradox.png)", "",
              "Strata are destination airport by month; the stratified estimate uses Mantel-Haenszel weights. "
              "On time follows DOT: cancelled and diverted flights count as late and stay in the denominator."]
    L += ["", "## Outputs", "", "- `bay_area_carrier_summary.csv`, `paradox_strata.csv`, `paradox_by_airport.csv`, "
          "`paradox_summary.json`, `paradox.png`", "- `reconciliation_vs_dot.csv`, `dq_exceptions.csv`", "- `runs/<run id>.json`: this run's record"]
    (out / "run_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    runs = out / "runs"
    runs.mkdir(exist_ok=True)
    record = {"run_id": run_id, "status": status, "started_utc": started.isoformat(timespec="seconds"),
              "config": cfg["config_file"].name, "load": load_result,
              "quality": dq.drop(columns="run_id").to_dict("records"),
              "reconciliation": None if rec is None else {"published": len(rec), "matched": int(rec.match.sum()),
                                                          "max_abs_difference_pts": float(rec.difference_pts.abs().max())},
              "paradox": None if par is None else par["result"]}
    (runs / f"{run_id}.json").write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
