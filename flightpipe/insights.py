"""Operational insights: run the SQL in sql/, save tables, draw the figures.

Writes outputs/tables/*.csv and outputs/figures/01-07*.png:
  01 on-time rate by carrier        02 carrier x month heatmap   03 delay causes by carrier
  04 delays by scheduled hour       05 busiest airports          06 cancellations by reason
  07 carrier-pair Simpson's paradox test (same origin airport and month)
"""
import itertools
import logging
import math
import sqlite3

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

from .config import ROOT

log = logging.getLogger("flightpipe.insights")
SQL_DIR = ROOT / "sql"
MONTHS = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun", 7: "Jul",
          8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e1", "#fcfcfb"
BLUE = "#2a78d6"
CAUSE_COLORS = {"Carrier": "#2a78d6", "Late aircraft": "#eb6834", "National Air System": "#1baf7a",
                "Weather": "#eda100", "Security": "#e87ba4"}
SEQ_BLUES = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
STYLE = {"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK_2,
         "xtick.color": INK_2, "ytick.color": INK_2, "axes.titlecolor": INK, "axes.titlesize": 11,
         "axes.titleweight": "bold", "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
         "savefig.facecolor": SURFACE}
Z = 1.96


def query(con, name):
    return pd.read_sql((SQL_DIR / name).read_text(encoding="utf-8"), con)


def tidy(ax, grid_axis="x"):
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def wilson(k, n, z=Z):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return 100 * (c - h), 100 * (c + h)


class Insights:
    def __init__(self, cfg):
        self.cfg = cfg
        out = cfg["paths"]["outputs"]
        self.tables, self.figures = out / "tables", out / "figures"
        self.tables.mkdir(parents=True, exist_ok=True)
        self.figures.mkdir(parents=True, exist_ok=True)

    def save(self, fig, name):
        fig.savefig(self.figures / name, dpi=160, bbox_inches="tight")
        plt.close(fig)

    def scorecard(self, con):
        t = query(con, "02_carrier_scorecard.sql")
        t.to_csv(self.tables / "carrier_scorecard.csv", index=False)
        t = t.sort_values("on_time_pct")
        fig, ax = plt.subplots(figsize=(7.5, 4.8))
        ax.barh(t.carrier_name, t.on_time_pct, color=BLUE, height=0.62)
        for y, v in enumerate(t.on_time_pct):
            ax.text(v + 0.4, y, f"{v:.1f}%", va="center", color=INK, fontsize=8)
        nat = 100 * con.execute("SELECT AVG(ON_TIME) FROM flights").fetchone()[0]
        ax.axvline(nat, color=INK_2, linestyle="--", linewidth=1)
        ax.text(nat, len(t) - 0.35, f" all carriers {nat:.1f}%", color=INK_2, fontsize=8)
        ax.set_xlim(50, 90)
        ax.set_xlabel("On-time arrivals, % of scheduled flights (DOT definition)")
        ax.set_title("On-time arrival rate by carrier, Jan-Jul 2026", loc="left")
        tidy(ax)
        self.save(fig, "01_carrier_on_time.png")
        return t

    def monthly_heatmap(self, con):
        t = query(con, "01_ontime_by_carrier_month.sql")
        t.to_csv(self.tables / "on_time_by_carrier_month.csv", index=False)
        m = t.pivot(index="carrier_name", columns="month", values="on_time_pct")
        m = m.loc[m.mean(axis=1).sort_values(ascending=False).index]
        # A carrier-month covering under half the month's days (e.g. an airline that stopped
        # flying) is marked with * so it isn't read as a full month.
        days_in_month = t.groupby("month").days_with_flights.transform("max")
        part = t[t.days_with_flights < 0.5 * days_in_month]
        partial = {(r.carrier_name, r.month) for r in part.itertuples()}
        fig, ax = plt.subplots(figsize=(7.5, 5.2))
        im = ax.imshow(m.values, cmap=LinearSegmentedColormap.from_list("blues", SEQ_BLUES), aspect="auto", vmin=50, vmax=90)
        ax.set_xticks(range(m.shape[1]), [MONTHS[c] for c in m.columns])
        ax.set_yticks(range(m.shape[0]), m.index)
        for i in range(m.shape[0]):
            for j in range(m.shape[1]):
                v = m.values[i, j]
                if not math.isnan(v):
                    star = "*" if (m.index[i], m.columns[j]) in partial else ""
                    ax.text(j, i, f"{v:.0f}{star}", ha="center", va="center", fontsize=8,
                            color="white" if v >= 74 else INK)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.tick_params(length=0)
        cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
        cb.outline.set_visible(False)
        cb.set_label("On-time %", color=INK_2)
        ax.set_title("On-time % by carrier and month (blank = no flights operated)", loc="left")
        if len(part):
            def span(r):
                d0, d1 = pd.Timestamp(r.first_date), pd.Timestamp(r.last_date)
                return f"{d0:%b} {d0.day}" + ("" if d0 == d1 else f" to {d1.day}")
            notes = "; ".join(f"{r.carrier_name}, flights on {span(r)} only "
                              f"({r.days_with_flights} day{'s' if r.days_with_flights > 1 else ''}, "
                              f"{r.scheduled_flights:,} flights)" for r in part.itertuples())
            fig.text(0.125, 0.015, f"* Part month: {notes}.", fontsize=7.5, color=INK_2, ha="left")
        self.save(fig, "02_on_time_heatmap.png")
        return t

    def delay_causes(self, con):
        t = query(con, "03_delay_causes_by_carrier.sql")
        cols = {"carrier_min": "Carrier", "late_aircraft_min": "Late aircraft", "nas_min": "National Air System",
                "weather_min": "Weather", "security_min": "Security"}
        t = t.rename(columns=cols)
        total = t[list(cols.values())].sum(axis=1)
        share = t[list(cols.values())].div(total, axis=0) * 100
        share.insert(0, "carrier_name", t.carrier_name)
        share["delay_min_per_flight"] = (total / t.scheduled_flights).round(1)
        share["controllable_share_pct"] = share["Carrier"] + share["Late aircraft"]
        share = share.round(1).sort_values("controllable_share_pct")
        share.to_csv(self.tables / "delay_cause_shares.csv", index=False)
        fig, ax = plt.subplots(figsize=(8.5, 5))
        left = pd.Series(0.0, index=share.index)
        for cause in cols.values():
            ax.barh(share.carrier_name, share[cause], left=left, height=0.62, color=CAUSE_COLORS[cause],
                    label=cause, edgecolor=SURFACE, linewidth=1.5)
            left += share[cause]
        for y, (_, r) in enumerate(share.iterrows()):
            ax.text(101, y, f"{r.controllable_share_pct:.0f}%", va="center", fontsize=8, color=INK)
        ax.text(101, len(share) - 0.3, "carrier +\nlate aircraft", fontsize=7, color=INK_2)
        ax.set_xlim(0, 112)
        ax.set_xlabel("Share of delay minutes (flights 15+ min late), %")
        ax.set_title("What causes the delay minutes, by carrier", loc="left")
        ax.legend(ncol=5, frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(0, -0.11))
        tidy(ax)
        self.save(fig, "03_delay_causes.png")
        return share

    def by_hour(self, con):
        t = query(con, "04_delay_by_departure_hour.sql")
        t = t[t.operated_flights >= 2000]           # drop thin overnight hours
        t.to_csv(self.tables / "delay_by_departure_hour.csv", index=False)
        if t.empty:
            return t
        fig, (a1, a2) = plt.subplots(2, 1, figsize=(8.5, 6.4), sharex=True,
                                     gridspec_kw={"height_ratios": [1, 1.3], "hspace": 0.25})
        line = t.set_index("dep_hour").on_time_pct.reindex(range(24))   # break the line over the gap
        a1.plot(line.index, line.values, color=BLUE, linewidth=2, marker="o", markersize=4)
        a1.set_ylabel("On-time %")
        a1.set_title("Delays build through the day", loc="left")
        tidy(a1, "y")
        bottom = pd.Series(0.0, index=t.index)
        for col, lab in [("mean_carrier_min", "Carrier"), ("mean_late_aircraft_min", "Late aircraft"),
                         ("mean_nas_min", "National Air System"), ("mean_weather_min", "Weather")]:
            a2.bar(t.dep_hour, t[col], bottom=bottom, color=CAUSE_COLORS[lab], width=0.75, label=lab,
                   edgecolor=SURFACE, linewidth=1.5)
            bottom += t[col]
        a2.set_ylabel("Delay minutes per operated flight")
        a2.set_xlabel("Scheduled departure hour (local time)")
        a2.set_xticks(t.dep_hour, [f"{h:02d}" for h in t.dep_hour])
        a2.legend(frameon=False, fontsize=8, ncol=4, loc="upper left", bbox_to_anchor=(0, -0.16))
        tidy(a2, "y")
        self.save(fig, "04_delay_by_hour.png")
        return t

    def airports(self, con):
        t = query(con, "05_airport_departures.sql")
        if t.empty:
            t.to_csv(self.tables / "airport_departure_performance.csv", index=False)
            return t
        t["on_time_dep_pct"] = 100 * t.on_time_departures / t.scheduled_departures
        t[["ci_low", "ci_high"]] = t.apply(lambda r: pd.Series(wilson(r.on_time_departures, r.scheduled_departures)), axis=1)
        t["cancelled_pct"] = 100 * t.cancelled / t.scheduled_departures
        t = t.round(2).sort_values("on_time_dep_pct")
        t.to_csv(self.tables / "airport_departure_performance.csv", index=False)
        fig, ax = plt.subplots(figsize=(7.5, 0.26 * len(t) + 1.2))
        y = range(len(t))
        ax.hlines(y, t.ci_low, t.ci_high, color=BLUE, linewidth=2)
        ax.plot(t.on_time_dep_pct, y, "o", color=BLUE, markersize=5, markeredgecolor=SURFACE, markeredgewidth=1.5)
        ax.set_yticks(list(y), [f"{a}  {str(c).split(',')[0]}" for a, c in zip(t.airport, t.city)], fontsize=8)
        allp = 100 * t.on_time_departures.sum() / t.scheduled_departures.sum()
        ax.axvline(allp, color=INK_2, linestyle="--", linewidth=1)
        ax.text(allp, len(t) - 0.2, f" these airports combined {allp:.1f}%", color=INK_2, fontsize=8)
        ax.set_xlabel("On-time departures, % of scheduled (95% Wilson interval)")
        ax.set_title(f"Departure performance at the {len(t)} busiest airports", loc="left")
        tidy(ax)
        self.save(fig, "05_airports.png")
        return t

    def cancellations(self, con):
        t = query(con, "06_cancellations_by_reason.sql")
        t.to_csv(self.tables / "cancellations_by_reason.csv", index=False)
        if t.empty:
            return t
        m = t.pivot(index="month", columns="reason", values="cancelled_flights").fillna(0)
        fig, ax = plt.subplots(figsize=(7.5, 4))
        bottom = pd.Series(0.0, index=m.index)
        for c in [c for c in ["Carrier", "National Air System", "Weather", "Security"] if c in m]:
            ax.bar([MONTHS[i] for i in m.index], m[c], bottom=bottom, width=0.6, color=CAUSE_COLORS[c], label=c,
                   edgecolor=SURFACE, linewidth=1.5)
            bottom += m[c]
        for i, v in enumerate(bottom):
            ax.text(i, v + 250, f"{v:,.0f}", ha="center", fontsize=8, color=INK)
        ax.set_ylabel("Cancelled flights")
        ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))
        ax.set_title("Cancellations by month and reason", loc="left")
        h, lab = ax.get_legend_handles_labels()
        ax.legend(h[::-1], lab[::-1], frameon=False, fontsize=8)   # match the stack order
        tidy(ax, "y")
        self.save(fig, "06_cancellations.png")
        return t

    def carrier_pairs(self, extract):
        """Does a carrier pair's overall ranking reverse at the same origin airport and month?"""
        p = {"pair_min_flights": 50, "pair_min_coverage": 0.5, **self.cfg.get("insights", {})}
        min_f, min_cov = p["pair_min_flights"], p["pair_min_coverage"]

        def compare(a, b):
            ca, cb = extract[extract.carrier_name == a], extract[extract.carrier_name == b]
            pa = ca.on_time_flights.sum() / ca.scheduled_flights.sum()
            pb = cb.on_time_flights.sum() / cb.scheduled_flights.sum()
            m = ca.merge(cb, on=["month", "origin_airport"], suffixes=("_a", "_b"))
            m = m[(m.scheduled_flights_a >= min_f) & (m.scheduled_flights_b >= min_f)]
            if m.empty:
                return None
            na, nb = m.scheduled_flights_a, m.scheduled_flights_b
            qa, qb = m.on_time_flights_a / na, m.on_time_flights_b / nb
            w = (na + nb) / (na + nb).sum()
            adj = float((w * (qa - qb)).sum())
            se = math.sqrt(float((w ** 2 * (qa * (1 - qa) / na + qb * (1 - qb) / nb)).sum()))
            lo, hi = adj - Z * se, adj + Z * se
            return dict(carrier_a=a, carrier_b=b, cells_compared=len(m),
                        coverage_a=na.sum() / ca.scheduled_flights.sum(), coverage_b=nb.sum() / cb.scheduled_flights.sum(),
                        overall_diff_pts=(pa - pb) * 100, adjusted_diff_pts=adj * 100,
                        adjusted_lo=lo * 100, adjusted_hi=hi * 100, cells_a_better=int((qa > qb).sum()),
                        reversal=bool(np.sign(pa - pb) != np.sign(adj) and (lo > 0 or hi < 0)))

        names = sorted(extract.carrier_name.unique())
        R = pd.DataFrame([r for a, b in itertools.combinations(names, 2) if (r := compare(a, b))])
        if R.empty:
            R = pd.DataFrame(columns=["carrier_a", "carrier_b", "reversal", "robust"])
            R.to_csv(self.tables / "simpsons_paradox_pairs.csv", index=False)
            return R
        R["robust"] = R.reversal & (R.coverage_a >= min_cov) & (R.coverage_b >= min_cov)
        R = R.sort_values(["robust", "reversal", "overall_diff_pts"], ascending=[False, False, False],
                          key=lambda s: s if s.dtype == bool else s.abs()).round(3)
        R.to_csv(self.tables / "simpsons_paradox_pairs.csv", index=False)
        top = R[R.robust].reindex(R[R.robust].overall_diff_pts.abs().sort_values(ascending=False).index)
        if len(top):
            r = top.iloc[0]
            fig, ax = plt.subplots(figsize=(7.2, 3.2))
            v = [r.overall_diff_pts, r.adjusted_diff_pts]
            ax.barh(["Overall", "Same airport\nand month"], v, color=["#9a9a95", BLUE])
            ax.errorbar(v[1], 1, xerr=[[v[1] - r.adjusted_lo], [r.adjusted_hi - v[1]]], color=INK, capsize=4)
            ax.axvline(0, color=INK, lw=0.8)
            ax.set_xlabel(f"On-time rate difference, {r.carrier_a} minus {r.carrier_b} (percentage points)")
            ax.set_title("Overall ranking vs. like-for-like comparison, Jan to Jul 2026")
            tidy(ax)
            fig.tight_layout()
            self.save(fig, "07_simpsons_paradox.png")
        return R


def run(cfg, run_id):
    plt.rcParams.update(STYLE)
    con = sqlite3.connect(cfg["paths"]["database"])
    names = cfg.get("carrier_names") or {k: v.title() for k, v in cfg["carriers"].items()}
    pd.DataFrame({"code": list(names), "carrier_name": list(names.values())}).to_sql(
        "carriers", con, if_exists="replace", index=False)
    con.executescript((SQL_DIR / "00_views.sql").read_text(encoding="utf-8"))
    ins = Insights(cfg)
    extract = query(con, "07_bi_extract.sql")
    extract.to_csv(ins.tables / "bi_extract_month_carrier_airport.csv", index=False)
    res = {"scorecard": ins.scorecard(con), "heatmap": ins.monthly_heatmap(con), "causes": ins.delay_causes(con),
           "hours": ins.by_hour(con), "airports": ins.airports(con), "cancellations": ins.cancellations(con),
           "pairs": ins.carrier_pairs(extract), "extract_rows": len(extract)}
    con.close()
    pr = res["pairs"]
    log.info("insights: 7 figures and %d tables written; %d of %d carrier pairs reverse (%d robust)",
             len(list(ins.tables.glob("*.csv"))), int(pr.reversal.sum()), len(pr), int(pr.robust.sum()))
    return res
