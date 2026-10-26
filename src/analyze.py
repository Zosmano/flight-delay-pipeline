"""Step 3: run the SQL analyses, save tables, and draw the figures."""
import math
import sqlite3

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
import pandas as pd

from config import DB_PATH, FIGURES_DIR, MONTH_NAMES, SQL_DIR, TABLES_DIR

# Palette: validated categorical order (slots 1-5) and one-hue blue ramp.
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e1", "#fcfcfb"
BLUE = "#2a78d6"
CAUSE_COLORS = {"Carrier": "#2a78d6", "Late aircraft": "#eb6834",
                "National Air System": "#1baf7a", "Weather": "#eda100",
                "Security": "#e87ba4"}
SEQ_BLUES = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": GRID,
    "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK_2,
    "axes.titlecolor": INK, "axes.titlesize": 11, "axes.titleweight": "bold",
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
})


def query(con, name):
    return pd.read_sql((SQL_DIR / name).read_text(), con)


def tidy(ax, grid_axis="x"):
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return 100 * (c - h), 100 * (c + h)


def save(fig, name):
    fig.savefig(FIGURES_DIR / name, dpi=160, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------- analyses
def scorecard(con):
    t = query(con, "02_carrier_scorecard.sql")
    t.to_csv(TABLES_DIR / "carrier_scorecard.csv", index=False)
    t = t.sort_values("on_time_pct")
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    ax.barh(t.carrier_name, t.on_time_pct, color=BLUE, height=0.62)
    for y, v in enumerate(t.on_time_pct):
        ax.text(v + 0.4, y, f"{v:.1f}%", va="center", color=INK, fontsize=8)
    nat = 100 * pd.read_sql("SELECT AVG(ON_TIME) v FROM flights", con).v[0]
    ax.axvline(nat, color=INK_2, linestyle="--", linewidth=1)
    ax.text(nat, len(t) - 0.35, f" all carriers {nat:.1f}%", color=INK_2, fontsize=8)
    ax.set_xlim(50, 90)
    ax.set_xlabel("On-time arrivals, % of scheduled flights (DOT definition)")
    ax.set_title("On-time arrival rate by carrier, Jan-Jul 2026", loc="left")
    tidy(ax)
    save(fig, "01_carrier_on_time.png")
    return t


def monthly_heatmap(con):
    t = query(con, "01_ontime_by_carrier_month.sql")
    t.to_csv(TABLES_DIR / "on_time_by_carrier_month.csv", index=False)
    m = t.pivot(index="carrier_name", columns="month", values="on_time_pct")
    m = m.loc[m.mean(axis=1).sort_values(ascending=False).index]
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("blues", SEQ_BLUES)
    fig, ax = plt.subplots(figsize=(7.5, 5.2))
    im = ax.imshow(m.values, cmap=cmap, aspect="auto", vmin=50, vmax=90)
    ax.set_xticks(range(m.shape[1]), [MONTH_NAMES[c] for c in m.columns])
    ax.set_yticks(range(m.shape[0]), m.index)
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = m.values[i, j]
            if not math.isnan(v):
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=8,
                        color="white" if v >= 74 else INK)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cb.outline.set_visible(False)
    cb.set_label("On-time %", color=INK_2)
    ax.set_title("On-time % by carrier and month (blank = not reported)", loc="left")
    save(fig, "02_on_time_heatmap.png")


def delay_causes(con):
    t = query(con, "03_delay_causes_by_carrier.sql")
    cols = {"carrier_min": "Carrier", "late_aircraft_min": "Late aircraft",
            "nas_min": "National Air System", "weather_min": "Weather",
            "security_min": "Security"}
    t = t.rename(columns=cols)
    total = t[list(cols.values())].sum(axis=1)
    share = t[list(cols.values())].div(total, axis=0) * 100
    share.insert(0, "carrier_name", t.carrier_name)
    share["delay_min_per_flight"] = (total / t.scheduled_flights).round(1)
    share["controllable_share_pct"] = share["Carrier"] + share["Late aircraft"]
    share = share.round(1).sort_values("controllable_share_pct")
    share.to_csv(TABLES_DIR / "delay_cause_shares.csv", index=False)

    fig, ax = plt.subplots(figsize=(8.5, 5))
    left = pd.Series(0.0, index=share.index)
    for cause in cols.values():
        ax.barh(share.carrier_name, share[cause], left=left, height=0.62,
                color=CAUSE_COLORS[cause], label=cause, edgecolor=SURFACE, linewidth=1.5)
        left += share[cause]
    for y, (_, r) in enumerate(share.iterrows()):
        ax.text(101, y, f"{r.controllable_share_pct:.0f}%", va="center", fontsize=8, color=INK)
    ax.text(101, len(share) - 0.3, "carrier +\nlate aircraft", fontsize=7, color=INK_2)
    ax.set_xlim(0, 112)
    ax.set_xlabel("Share of delay minutes (flights 15+ min late), %")
    ax.set_title("What causes the delay minutes, by carrier", loc="left")
    ax.legend(ncol=5, frameon=False, fontsize=8, loc="upper left",
              bbox_to_anchor=(0, -0.11))
    tidy(ax)
    save(fig, "03_delay_causes.png")
    return share


def by_hour(con):
    t = query(con, "04_delay_by_departure_hour.sql")
    t = t[t.operated_flights >= 2000]           # drop thin overnight hours
    t.to_csv(TABLES_DIR / "delay_by_departure_hour.csv", index=False)
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8.5, 6.4), sharex=True,
                                 gridspec_kw={"height_ratios": [1, 1.3], "hspace": 0.25})
    # Reindex to every hour so the line breaks across the thin overnight gap.
    line = t.set_index("dep_hour").on_time_pct.reindex(range(24))
    a1.plot(line.index, line.values, color=BLUE, linewidth=2, marker="o", markersize=4)
    a1.set_ylabel("On-time %")
    a1.set_title("Delays build through the day", loc="left")
    tidy(a1, "y")
    parts = [("mean_carrier_min", "Carrier"), ("mean_late_aircraft_min", "Late aircraft"),
             ("mean_nas_min", "National Air System"), ("mean_weather_min", "Weather")]
    bottom = pd.Series(0.0, index=t.index)
    for col, lab in parts:
        a2.bar(t.dep_hour, t[col], bottom=bottom, color=CAUSE_COLORS[lab], width=0.75,
               label=lab, edgecolor=SURFACE, linewidth=1.5)
        bottom += t[col]
    a2.set_ylabel("Delay minutes per operated flight")
    a2.set_xlabel("Scheduled departure hour (local time)")
    a2.set_xticks(t.dep_hour, [f"{h:02d}" for h in t.dep_hour])
    a2.legend(frameon=False, fontsize=8, ncol=4, loc="upper left",
              bbox_to_anchor=(0, -0.16))
    tidy(a2, "y")
    save(fig, "04_delay_by_hour.png")
    return t


def airports(con):
    t = query(con, "05_airport_departures.sql")
    t["on_time_dep_pct"] = 100 * t.on_time_departures / t.scheduled_departures
    t[["ci_low", "ci_high"]] = t.apply(
        lambda r: pd.Series(wilson(r.on_time_departures, r.scheduled_departures)), axis=1)
    t["cancelled_pct"] = 100 * t.cancelled / t.scheduled_departures
    t = t.round(2).sort_values("on_time_dep_pct")
    t.to_csv(TABLES_DIR / "airport_departure_performance.csv", index=False)
    fig, ax = plt.subplots(figsize=(7.5, 0.26 * len(t) + 1.2))
    y = range(len(t))
    ax.hlines(y, t.ci_low, t.ci_high, color=BLUE, linewidth=2)
    ax.plot(t.on_time_dep_pct, y, "o", color=BLUE, markersize=5,
            markeredgecolor=SURFACE, markeredgewidth=1.5)
    ax.set_yticks(list(y), [f"{a}  {c.split(',')[0]}" for a, c in zip(t.airport, t.city)],
                  fontsize=8)
    allp = 100 * t.on_time_departures.sum() / t.scheduled_departures.sum()
    ax.axvline(allp, color=INK_2, linestyle="--", linewidth=1)
    ax.text(allp, len(t) - 0.2, f" these airports combined {allp:.1f}%", color=INK_2, fontsize=8)
    ax.set_xlabel("On-time departures, % of scheduled (95% Wilson interval)")
    ax.set_title(f"Departure performance at the {len(t)} busiest airports", loc="left")
    tidy(ax)
    save(fig, "05_airports.png")
    return t


def cancellations(con):
    t = query(con, "06_cancellations_by_reason.sql")
    t.to_csv(TABLES_DIR / "cancellations_by_reason.csv", index=False)
    m = t.pivot(index="month", columns="reason", values="cancelled_flights").fillna(0)
    order = [c for c in ["Carrier", "National Air System", "Weather", "Security"] if c in m]
    fig, ax = plt.subplots(figsize=(7.5, 4))
    bottom = pd.Series(0.0, index=m.index)
    for c in order:
        ax.bar([MONTH_NAMES[i] for i in m.index], m[c], bottom=bottom, width=0.6,
               color=CAUSE_COLORS[c], label=c, edgecolor=SURFACE, linewidth=1.5)
        bottom += m[c]
    for i, v in enumerate(bottom):
        ax.text(i, v + 250, f"{v:,.0f}", ha="center", fontsize=8, color=INK)
    ax.set_ylabel("Cancelled flights")
    ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))
    ax.set_title("Cancellations by month and reason", loc="left")
    h, l = ax.get_legend_handles_labels()
    ax.legend(h[::-1], l[::-1], frameon=False, fontsize=8)   # match stack order
    tidy(ax, "y")
    save(fig, "06_cancellations.png")
    return m


def bi_extract(con):
    t = query(con, "07_tableau_extract.sql")
    t.to_csv(TABLES_DIR / "bi_extract_month_carrier_airport.csv", index=False)
    return t


def run():
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    results = {
        "scorecard": scorecard(con),
        "causes": delay_causes(con),
        "hours": by_hour(con),
        "airports": airports(con),
        "cancellations": cancellations(con),
        "extract_rows": len(bi_extract(con)),
    }
    monthly_heatmap(con)
    con.close()
    print(f"  analysis: tables in {TABLES_DIR.name}/, figures in {FIGURES_DIR.name}/")
    return results


if __name__ == "__main__":
    run()
