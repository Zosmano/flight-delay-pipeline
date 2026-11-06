import json
import sqlite3

import numpy as np
import pandas as pd
import pytest

from conftest import flight, write_month
from flightpipe import __main__ as cli
from flightpipe import load, paradox, quality, reference


def count(cfg, sql="SELECT COUNT(*) FROM flights"):
    with sqlite3.connect(cfg["paths"]["database"]) as con:
        return con.execute(sql).fetchone()[0]


def test_dot_on_time_definition_keeps_cancelled_and_diverted_in_denominator():
    rows = pd.DataFrame([flight(arr_delay=14), flight(arr_delay=15), flight(cancelled=1, code="B"),
                         flight(diverted=1)])
    out = load.prepare(rows, "x.csv")
    assert out.ON_TIME.tolist() == [1, 0, 0, 0]
    assert out.OPERATED.tolist() == [1, 1, 0, 0]


def test_load_is_incremental_and_idempotent(cfg):
    raw = cfg["paths"]["raw_dir"]
    rows = [flight(day=d, arr_delay=d) for d in range(1, 8)]
    write_month(raw, rows + [rows[0]])                      # one exact duplicate row
    first = load.run(cfg)
    assert count(cfg) == 7 and first["files"][0]["duplicates"] == 1
    second = load.run(cfg)                                  # unchanged file: skipped
    assert second["files"][0]["action"] == "skipped" and count(cfg) == 7
    write_month(raw, rows + [flight(day=9)])                # BTS revises the month
    load.run(cfg)
    assert count(cfg) == 8
    assert count(cfg, "SELECT COUNT(*) FROM load_manifest") == 1


def test_quality_checks_pass_on_clean_data_and_fail_on_bad_codes(cfg):
    write_month(cfg["paths"]["raw_dir"], [flight(), flight(day=2, cancelled=1, code="B")])
    res = quality.run(cfg, "t1", load.run(cfg))
    assert len(res) == 12 and set(res.status) == {"pass"}
    write_month(cfg["paths"]["raw_dir"], [flight(), flight(day=2, cancelled=1, code="Z"),
                                           flight(day=3, carrier="XX")])
    res = quality.run(cfg, "t2", load.run(cfg)).set_index("check_id")
    assert res.loc["DQ-07", "status"] == "fail" and res.loc["DQ-05", "status"] == "fail"


def test_schema_problem_is_reported(cfg):
    pd.DataFrame({"FL_DATE": ["1/1/2026"], "MONTH": [1]}).to_csv(cfg["paths"]["raw_dir"] / "broken.csv", index=False)
    files, problems = load.discover(cfg["paths"]["raw_dir"])
    assert files == [] and problems[0]["file"] == "broken.csv"


def test_bad_data_stops_the_run_with_exit_code_2(workspace):
    write_month(workspace / "raw", [flight(cancelled=1, code="Z")])
    assert cli.main(["run", "--config", str(workspace / "pipeline.toml")]) == 2


def test_mantel_haenszel_matches_hand_calculation():
    # stratum 1: A 90/100 vs B 80/100; stratum 2: A 50/100 vs B 40/300
    est, se = paradox.mantel_haenszel([90, 50], [100, 100], [80, 40], [100, 300])
    w = np.array([50, 75])
    assert est == pytest.approx((w[0] * 0.10 + w[1] * (0.5 - 40 / 300)) / w.sum())
    assert se > 0


def test_end_to_end_finds_a_constructed_simpsons_paradox(workspace):
    # SkyWest flies mostly into hard SFO, Southwest mostly into easy OAK. SkyWest is
    # better at both airports but worse once the airports are pooled.
    rows = []
    for d in range(1, 21):
        rows += [flight(day=d, carrier="OO", dest="SFO", arr_delay=0 if d <= 12 else 30) for _ in range(5)]
        rows += [flight(day=d, carrier="OO", dest="OAK", arr_delay=0)]
        rows += [flight(day=d, carrier="WN", dest="OAK", arr_delay=0 if d <= 18 else 30) for _ in range(5)]
        rows += [flight(day=d, carrier="WN", dest="SFO", arr_delay=0 if d <= 8 else 30)]
    rows = [dict(r, TAIL_NUM=f"N{i}") for i, r in enumerate(rows)]  # keep rows distinct
    write_month(workspace / "raw", rows)
    pd.DataFrame([{"year": 2026, "month": 1, "carrier_name": "SKYWEST AIRLINES", "published_on_time_pct": 66.7,
                   "source_report": "test", "source_table": "typed in"},
                  {"year": 2026, "month": 1, "carrier_name": "SOUTHWEST AIRLINES", "published_on_time_pct": 81.7,
                   "source_report": "test", "source_table": "typed in"}]).to_csv(workspace / "manual.csv", index=False)
    assert cli.main(["run", "--config", str(workspace / "pipeline.toml")]) == 0
    res = json.loads((workspace / "out" / "paradox_summary.json").read_text())
    assert res["crude_diff_pts"]["estimate"] < 0 < res["stratified_diff_pts"]["estimate"]
    assert res["paradox"] is True
    assert (workspace / "out" / "run_report.md").exists()
    assert len(pd.read_csv(workspace / "out" / "bay_area_carrier_summary.csv")) == 4


TABLE_1A = """7 \nAIR TRAVEL CONSUMER REPORT \nTABLE 1A. OVERALL PERCENTAGE OF REPORTED FLIGHT OPERATIONS ARRIVING ON-TIME BY REPORTING OPERATING CARRIER \n
JULY 2026 \n \nAT ALL US AIRPORTS \nCARRIER1 \nNUMBER OF \nAIRPORTS \nREPORTED \nPERCENT OF ON-TIME \nARRIVALS \nRANK \n  ENVOY AIR \n154 \n  \n79.8 \n1 \n
  ALASKA AIRLINES2 \n85 \n  \n75.9 \n2 \nTOTAL AIRPORTS SERVED \n352 \n  \n69.4 \n"""

TABLE_1B = """TABLE 1B. OVERALL PERCENTAGE OF REPORTED FLIGHT OPERATIONS ARRIVING ON-TIME BY REPORTING MARKETING CARRIER RANK BY MONTH, AND YEAR-TO-DATE \n
JULY 2026 \nCARRIER1 \nJan 26 \nFeb 26 \nYear-to-date \n(YTD) \n% \nRank \n% \nRank \n% \nRank \n  ALASKA AIRLINES2  \n77.9 \n2 \n82.4 \n1 \n79.6 \n1 \n
  - ALASKA AIRLINES \n77.1 \n  \n81.7 \n  \n79.5 \n  \n  - BRANDED CODESHARE PARTNERS \n79.5 \n  \n83.8 \n  \n79.7 \n  \n  SOUTHWEST AIRLINES  \n82.4 \n1 \n80.8 \n3 \n73.7 \n4 \n
  SPIRIT AIRLINES  \n66.6 \n8 \nN/A \nN/A \nN/A \nN/A \nTOTAL \n75.3 \n   \n78.5 \n   \n75.1 \n \n1 All U.S. airlines"""


def test_parse_table_1a():
    t = reference.parse_table_1a(TABLE_1A, "Sep")
    assert t[["month", "carrier_name", "published_on_time_pct"]].values.tolist() == [
        [7, "ENVOY AIR", 79.8], [7, "ALASKA AIRLINES", 75.9], [7, "ALL CARRIERS", 69.4]]


def test_parse_table_1b_uses_own_flight_rows():
    t = reference.parse_table_1b(TABLE_1B, "Sep").set_index(["month", "carrier_name"]).published_on_time_pct
    assert t[(1, "ALASKA AIRLINES")] == 77.1          # the "- ALASKA AIRLINES" row, not 77.9
    assert t[(2, "SOUTHWEST AIRLINES")] == 80.8
    assert (2, "SPIRIT AIRLINES") not in t.index      # N/A is skipped
    assert not any("BRANDED" in c for _, c in t.index)
