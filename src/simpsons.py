"""Step 4 (optional): test every carrier pair for a Simpson's paradox.

Question: does the overall on-time ranking of two carriers reverse when they are compared
at the same origin airport in the same month? Uses the month x carrier x origin-airport
extract (outputs/tables/bi_extract_month_carrier_airport.csv), so it needs no database.

For carriers A and B:
  overall difference  = on-time rate of A minus B across all of their flights
  adjusted difference = weighted mean of (rate A - rate B) over airport-month cells where both
                        carriers have at least MIN_FLIGHTS flights, each cell weighted by the
                        combined flights of A and B
A pair is flagged as a reversal when the two differences have opposite signs and the 95%
interval of the adjusted difference excludes zero.
On time follows the DOT definition used in the rest of this repository: cancelled and
diverted flights count as not on time.
"""
import itertools
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config import FIGURES_DIR, TABLES_DIR

MIN_FLIGHTS = 50      # minimum flights per carrier in an airport-month cell
MIN_COVERAGE = 0.50   # share of each carrier's flights that the compared cells must cover
Z = 1.96


def compare(d, a, b):
    ca, cb = d[d.carrier_name == a], d[d.carrier_name == b]
    pa, pb = ca.on_time_flights.sum() / ca.scheduled_flights.sum(), cb.on_time_flights.sum() / cb.scheduled_flights.sum()
    m = ca.merge(cb, on=["month", "origin_airport"], suffixes=("_a", "_b"))
    m = m[(m.scheduled_flights_a >= MIN_FLIGHTS) & (m.scheduled_flights_b >= MIN_FLIGHTS)]
    if m.empty:
        return None
    na, nb = m.scheduled_flights_a, m.scheduled_flights_b
    qa, qb = m.on_time_flights_a / na, m.on_time_flights_b / nb
    w = (na + nb) / (na + nb).sum()
    adj = float((w * (qa - qb)).sum())
    se = math.sqrt(float((w ** 2 * (qa * (1 - qa) / na + qb * (1 - qb) / nb)).sum()))
    cov_a, cov_b = na.sum() / ca.scheduled_flights.sum(), nb.sum() / cb.scheduled_flights.sum()
    lo, hi = adj - Z * se, adj + Z * se
    return dict(carrier_a=a, carrier_b=b, cells_compared=len(m), coverage_a=cov_a, coverage_b=cov_b,
                overall_diff_pts=(pa - pb) * 100, adjusted_diff_pts=adj * 100,
                adjusted_lo=lo * 100, adjusted_hi=hi * 100,
                cells_a_better=int((qa > qb).sum()),
                reversal=bool(np.sign(pa - pb) != np.sign(adj) and (lo > 0 or hi < 0)))


def main():
    d = pd.read_csv(TABLES_DIR / "bi_extract_month_carrier_airport.csv")
    pairs = [r for a, b in itertools.combinations(sorted(d.carrier_name.unique()), 2) if (r := compare(d, a, b))]
    R = pd.DataFrame(pairs)
    R["robust"] = R.reversal & (R.coverage_a >= MIN_COVERAGE) & (R.coverage_b >= MIN_COVERAGE)
    R = R.sort_values(["robust", "reversal", "overall_diff_pts"], ascending=[False, False, False],
                      key=lambda s: s if s.dtype == bool else s.abs()).round(3)
    R.to_csv(TABLES_DIR / "simpsons_paradox_pairs.csv", index=False)
    print(f"{len(R)} carrier pairs tested | {int(R.reversal.sum())} reversals | "
          f"{int(R.robust.sum())} with at least {MIN_COVERAGE:.0%} of both carriers' flights compared")
    top = R[R.robust].reindex(R[R.robust].overall_diff_pts.abs().sort_values(ascending=False).index).head(3)
    print(top[["carrier_a", "carrier_b", "cells_compared", "coverage_a", "coverage_b",
               "overall_diff_pts", "adjusted_diff_pts", "adjusted_lo", "adjusted_hi", "cells_a_better"]].to_string(index=False))
    if len(top):
        r = top.iloc[0]
        fig, ax = plt.subplots(figsize=(7.2, 3.2))
        v = [r.overall_diff_pts, r.adjusted_diff_pts]
        ax.barh(["Overall", "Same airport\nand month"], v, color=["#9a9a95", "#2a78d6"])
        ax.errorbar(v[1], 1, xerr=[[v[1] - r.adjusted_lo], [r.adjusted_hi - v[1]]], color="#0b0b0b", capsize=4)
        ax.axvline(0, color="#0b0b0b", lw=0.8)
        ax.set_xlabel(f"On-time rate difference, {r.carrier_a} minus {r.carrier_b} (percentage points)")
        ax.set_title("Overall ranking vs. like-for-like comparison, Jan to Jul 2026")
        fig.tight_layout()
        fig.savefig(FIGURES_DIR / "07_simpsons_paradox.png", dpi=150)


if __name__ == "__main__":
    main()
