"""Simpson's paradox test: carrier A vs carrier B on arrivals into a set of airports.

The crude comparison pools every arrival. The stratified comparison holds the destination
airport and month fixed: one stratum per airport-by-month group (3 airports x 7 months = 21),
and the stratum differences are combined with Mantel-Haenszel weights n_a*n_b/(n_a+n_b).
95% intervals: Wald (flights treated as independent) and a cluster bootstrap that resamples
whole days, because flights on the same day share weather and air-traffic delays.
"""
import json
import logging
import sqlite3

import numpy as np
import pandas as pd

log = logging.getLogger("flightpipe.paradox")
Z = 1.959963984540054

SQL = """
SELECT MONTH AS month, DEST AS airport, OP_UNIQUE_CARRIER AS carrier, FL_DATE AS day,
       COUNT(*) AS flights, SUM(ON_TIME) AS on_time
FROM flights
WHERE DEST IN ({a}) AND OP_UNIQUE_CARRIER IN (?, ?)
GROUP BY MONTH, DEST, OP_UNIQUE_CARRIER, FL_DATE
"""


def diff_ci(xa, na, xb, nb):
    pa, pb = xa / na, xb / nb
    d = pa - pb
    se = np.sqrt(pa * (1 - pa) / na + pb * (1 - pb) / nb)
    return d, se


def mantel_haenszel(xa, na, xb, nb):
    """Weighted mean of stratum differences and its standard error (independent strata)."""
    xa, na, xb, nb = map(np.asarray, (xa, na, xb, nb))
    d, se = diff_ci(xa, na, xb, nb)
    w = na * nb / (na + nb)
    est = np.sum(w * d) / np.sum(w)
    return est, np.sqrt(np.sum(w ** 2 * se ** 2)) / np.sum(w)


def run(cfg, run_id):
    p = cfg["paradox"]
    a, b, airports = p["carrier_a"], p["carrier_b"], p["airports"]
    disp = cfg.get("display_names", {})
    names = {k: disp.get(k, cfg["carriers"].get(k, k).title()) for k in (a, b)}
    short = names
    con = sqlite3.connect(cfg["paths"]["database"])
    raw = pd.read_sql(SQL.format(a=",".join("?" * len(airports))), con, params=[*airports, a, b])
    con.close()
    out = cfg["paths"]["outputs"]
    out.mkdir(parents=True, exist_ok=True)

    # 1. Summary table: monthly and overall on-time rate, pooled across the airports.
    def rates(df, by):
        t = df.groupby(by, as_index=False)[["flights", "on_time"]].sum()
        t["on_time_rate_pct"] = (100 * t.on_time / t.flights).round(2)
        return t
    monthly = rates(raw, ["month", "carrier"])
    monthly["period"] = monthly.month.map(lambda m: f"{cfg['load']['year']}-{m:02d}")
    overall = rates(raw, ["carrier"]).assign(period=f"{cfg['load']['year']} Jan-Jul overall")
    summary = pd.concat([monthly, overall], ignore_index=True)
    summary["carrier"] = summary.carrier.map(short)
    summary = summary.rename(columns={"flights": "scheduled_flights", "on_time": "on_time_flights"})[
        ["period", "carrier", "scheduled_flights", "on_time_flights", "on_time_rate_pct"]]
    summary.to_csv(out / "bay_area_carrier_summary.csv", index=False)

    # 2. Strata: one row per airport-by-month group.
    cell = raw.groupby(["month", "airport", "carrier"])[["flights", "on_time"]].sum().unstack("carrier")
    s = pd.DataFrame({"n_a": cell["flights"][a], "x_a": cell["on_time"][a],
                      "n_b": cell["flights"][b], "x_b": cell["on_time"][b]}).fillna(0).reset_index()
    keep = (s.n_a >= p["min_flights_per_carrier"]) & (s.n_b >= p["min_flights_per_carrier"])
    dropped = s[~keep]
    s = s[keep].reset_index(drop=True)
    d, se = diff_ci(s.x_a, s.n_a, s.x_b, s.n_b)
    s["rate_a_pct"], s["rate_b_pct"] = 100 * s.x_a / s.n_a, 100 * s.x_b / s.n_b
    s["diff_pts"], s["ci_low"], s["ci_high"] = 100 * d, 100 * (d - Z * se), 100 * (d + Z * se)
    s["weight"] = s.n_a * s.n_b / (s.n_a + s.n_b)
    s["weight_share"] = s.weight / s.weight.sum()
    s.round(3).rename(columns={"n_a": f"flights_{a}", "x_a": f"on_time_{a}", "n_b": f"flights_{b}",
                               "x_b": f"on_time_{b}"}).to_csv(out / "paradox_strata.csv", index=False)

    # 3. Crude vs stratified, with Wald and day-cluster bootstrap intervals.
    tot = raw.groupby("carrier")[["flights", "on_time"]].sum()
    crude, crude_se = diff_ci(tot.on_time[a], tot.flights[a], tot.on_time[b], tot.flights[b])
    mh, mh_se = mantel_haenszel(s.x_a, s.n_a, s.x_b, s.n_b)
    boot = bootstrap(raw, s, a, b, p["bootstrap_reps"], p["seed"])

    by_airport = []
    for ap, g in s.groupby("airport"):
        e, e_se = mantel_haenszel(g.x_a, g.n_a, g.x_b, g.n_b)
        ta = raw[(raw.airport == ap)].groupby("carrier")[["flights", "on_time"]].sum()
        by_airport.append({"airport": ap, f"flights_{a}": int(ta.flights[a]), f"flights_{b}": int(ta.flights[b]),
                           f"rate_{a}_pct": 100 * ta.on_time[a] / ta.flights[a],
                           f"rate_{b}_pct": 100 * ta.on_time[b] / ta.flights[b],
                           "share_of_a_flights": ta.flights[a] / tot.flights[a],
                           "share_of_b_flights": ta.flights[b] / tot.flights[b],
                           "stratified_diff_pts": 100 * e, "ci_low": 100 * (e - Z * e_se),
                           "ci_high": 100 * (e + Z * e_se)})
    by_airport = pd.DataFrame(by_airport)
    by_airport.round(4).to_csv(out / "paradox_by_airport.csv", index=False)

    mrates = monthly.pivot(index="month", columns="carrier", values="on_time_rate_pct")
    led = mrates.index[mrates[a] > mrates[b]].tolist()
    res = {
        "run_id": run_id, "carrier_a": names[a], "carrier_b": names[b], "airports": airports,
        "flights": {names[a]: int(tot.flights[a]), names[b]: int(tot.flights[b])},
        "pooled_rate_pct": {names[a]: 100 * tot.on_time[a] / tot.flights[a],
                            names[b]: 100 * tot.on_time[b] / tot.flights[b]},
        "crude_diff_pts": {"estimate": 100 * crude, "ci_wald": [100 * (crude - Z * crude_se), 100 * (crude + Z * crude_se)],
                           "ci_day_bootstrap": boot["crude"]},
        "stratified_diff_pts": {"estimate": 100 * mh, "ci_wald": [100 * (mh - Z * mh_se), 100 * (mh + Z * mh_se)],
                                "ci_day_bootstrap": boot["mh"]},
        "strata_used": int(len(s)), "strata_dropped": int(len(dropped)),
        "strata_where_a_leads": int((s.diff_pts > 0).sum()),
        "strata_where_a_leads_significantly": int((s.ci_low > 0).sum()),
        "strata_where_b_leads_significantly": int((s.ci_high < 0).sum()),
        "months_a_led_pooled": led,
        "bootstrap": {"reps": p["bootstrap_reps"], "seed": p["seed"], "cluster": "flight date"},
    }
    res["paradox"] = bool(np.sign(crude) != np.sign(mh) and
                          (res["stratified_diff_pts"]["ci_wald"][0] > 0 or res["stratified_diff_pts"]["ci_wald"][1] < 0))
    (out / "paradox_summary.json").write_text(json.dumps(res, indent=2, default=float))
    chart(s, by_airport, res, a, b, short, out / "paradox.png")
    log.info("paradox: pooled %+.1f pts, stratified %+.1f pts (%s minus %s), %d of %d strata favour %s",
             100 * crude, 100 * mh, short[a], short[b], res["strata_where_a_leads"], len(s), short[a])
    return {"summary": summary, "strata": s, "by_airport": by_airport, "result": res}


def bootstrap(raw, s, a, b, reps, seed):
    """Resample flight dates with replacement; every flight on a drawn date comes along."""
    strata = list(zip(s.month, s.airport))
    sid = {k: i for i, k in enumerate(strata)}
    r = raw[[k in sid for k in zip(raw.month, raw.airport)]].copy()
    r["sid"] = [sid[k] for k in zip(r.month, r.airport)]
    days = sorted(r.day.unique())
    did = {d: i for i, d in enumerate(days)}
    arr = np.zeros((len(days), len(strata), 4))
    for row in r.itertuples():
        j = 0 if row.carrier == a else 2
        arr[did[row.day], row.sid, j] += row.flights
        arr[did[row.day], row.sid, j + 1] += row.on_time
    rng = np.random.default_rng(seed)
    month_of_day = np.array([int(d[5:7]) for d in days])
    crude, mh = [], []
    for _ in range(reps):
        # resample within each month so every airport-by-month stratum stays populated
        idx = np.concatenate([rng.choice(np.flatnonzero(month_of_day == m), size=(month_of_day == m).sum())
                              for m in np.unique(month_of_day)])
        t = arr[idx].sum(axis=0)
        na, xa, nb, xb = t[:, 0], t[:, 1], t[:, 2], t[:, 3]
        crude.append(xa.sum() / na.sum() - xb.sum() / nb.sum())
        w = na * nb / (na + nb)
        mh.append(np.sum(w * (xa / na - xb / nb)) / np.sum(w))
    pct = lambda v: [float(100 * np.percentile(v, 2.5)), float(100 * np.percentile(v, 97.5))]
    return {"crude": pct(crude), "mh": pct(mh)}


def chart(s, by_airport, res, a, b, short, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ca, cb, ink, muted = "#eb6834", "#2a78d6", "#1f2328", "#6b7280"
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5.2), gridspec_kw={"width_ratios": [1, 1.25]})
    groups = ["All three\n(pooled)"] + list(by_airport.airport)
    va = [res["pooled_rate_pct"][res["carrier_a"]]] + list(by_airport[f"rate_{a}_pct"])
    vb = [res["pooled_rate_pct"][res["carrier_b"]]] + list(by_airport[f"rate_{b}_pct"])
    x = np.arange(len(groups))
    ax1.bar(x - 0.19, vb, 0.36, color=cb, label=short[b])
    ax1.bar(x + 0.19, va, 0.36, color=ca, label=short[a])
    for i in range(len(groups)):
        ax1.text(i - 0.19, vb[i] + 1, f"{vb[i]:.1f}", ha="center", fontsize=9, color=ink)
        ax1.text(i + 0.19, va[i] + 1, f"{va[i]:.1f}", ha="center", fontsize=9, color=ink)
    ax1.set_xticks(x, groups)
    ax1.set_ylim(0, 100)
    ax1.set_ylabel("On-time arrivals (%)")
    pooled_lead = short[a] if va[0] > vb[0] else short[b]
    ap_lead = {short[a] if x > y else short[b] for x, y in zip(va[1:], vb[1:])}
    ap_text = f"{ap_lead.pop()} leads at every airport" if len(ap_lead) == 1 else "the lead varies by airport"
    ax1.set_title(f"Pooled, {pooled_lead} leads; {ap_text}", fontsize=11, color=ink, loc="left")
    ax1.legend(frameon=False, loc="upper left")
    s = s.sort_values(["airport", "month"]).reset_index(drop=True)
    y = np.arange(len(s))[::-1]
    ax2.errorbar(s.diff_pts, y, xerr=[s.diff_pts - s.ci_low, s.ci_high - s.diff_pts], fmt="o", color=ca,
                 ecolor=muted, ms=4, capsize=2)
    ax2.axvline(0, color=ink, lw=1)
    st = res["stratified_diff_pts"]
    ax2.axvline(st["estimate"], color=ca, lw=1, ls="--")
    ax2.axvline(res["crude_diff_pts"]["estimate"], color=cb, lw=1, ls="--")
    ax2.set_ylim(-1, len(s) + 0.6)
    ax2.text(st["estimate"], len(s) - 0.1, f" stratified {st['estimate']:+.1f}", color=ca, fontsize=9)
    ax2.text(res["crude_diff_pts"]["estimate"], len(s) - 0.1, f" pooled {res['crude_diff_pts']['estimate']:+.1f}",
             color=cb, fontsize=9)
    ax2.set_yticks(y, [f"{ap} {pd.Timestamp(2026, m, 1):%b}" for ap, m in zip(s.airport, s.month)], fontsize=8)
    ax2.set_xlabel(f"{short[a]} minus {short[b]}, on-time points (95% CI)")
    ax2.set_title("21 airport-by-month groups", fontsize=11, color=ink, loc="left")
    for ax in (ax1, ax2):
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
