"""A tiny synthetic BTS month, lookups and config, so the tests run without the real data."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from flightpipe import config  # noqa: E402

COLS = config.FLIGHT_COLS


def flight(month=1, day=1, carrier="WN", dest="OAK", arr_delay=0.0, cancelled=0, diverted=0, code=None, **kw):
    late = arr_delay is not None and arr_delay >= 15
    row = {"YEAR": 2026, "MONTH": month, "FL_DATE": f"{month}/{day}/2026 12:00:00 AM", "OP_UNIQUE_CARRIER": carrier,
           "TAIL_NUM": "N1", "ORIGIN": "LAX", "DEST": dest, "CRS_DEP_TIME": 900, "DEP_TIME": 900,
           "DEP_DELAY": 0, "CRS_ARR_TIME": 1100, "ARR_TIME": None if cancelled else 1100,
           "ARR_DELAY": None if cancelled or diverted else arr_delay,
           "ARR_DEL15": None if cancelled or diverted else float(late),
           "CANCELLED": cancelled, "CANCELLATION_CODE": code, "DIVERTED": diverted, "DISTANCE": 300,
           "CARRIER_DELAY": arr_delay if late else None, "WEATHER_DELAY": 0 if late else None,
           "NAS_DELAY": 0 if late else None, "SECURITY_DELAY": 0 if late else None,
           "LATE_AIRCRAFT_DELAY": 0 if late else None}
    if cancelled:
        row["ARR_DELAY"] = row["ARR_DEL15"] = None
    row.update(kw)
    return row


def write_month(folder, rows, name="T_ONTIME_REPORTING_Jan.csv"):
    pd.DataFrame(rows, columns=COLS).to_csv(Path(folder) / name, index=False)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Tests must never read the real data folder, whatever the shell has set."""
    monkeypatch.delenv("FLIGHTPIPE_RAW_DIR", raising=False)
    monkeypatch.delenv("FLIGHTPIPE_CONFIG", raising=False)


@pytest.fixture
def workspace(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    pd.DataFrame({"Code": ["WN", "OO"], "Description": ["Southwest", "SkyWest"]}).to_csv(raw / "L_UNIQUE_CARRIERS.csv", index=False)
    pd.DataFrame({"Code": ["LAX", "OAK", "SFO", "SJC"], "Description": list("abcd")}).to_csv(raw / "L_AIRPORT.csv", index=False)
    pd.DataFrame({"Code": list("ABCD"), "Description": list("wxyz")}).to_csv(raw / "L_CANCELLATION.csv", index=False)
    (tmp_path / "pdfs").mkdir()
    (tmp_path / "pipeline.toml").write_text("""
[paths]
raw_dir = "raw"
reference_dir = "pdfs"
manual_reference = "manual.csv"
database = "flights.db"
outputs = "out"
logs = "logs"
[load]
year = 2026
chunk_rows = 3
[reconcile]
tolerance_pts = 0.05
[carriers]
WN = "SOUTHWEST AIRLINES"
OO = "SKYWEST AIRLINES"
[display_names]
OO = "SkyWest"
WN = "Southwest"
[paradox]
airports = ["OAK", "SFO"]
carrier_a = "OO"
carrier_b = "WN"
min_flights_per_carrier = 1
bootstrap_reps = 50
seed = 1
""")
    return tmp_path


@pytest.fixture
def cfg(workspace):
    return config.load(workspace / "pipeline.toml")
