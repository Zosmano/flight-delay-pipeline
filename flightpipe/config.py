"""Read pipeline.toml and resolve its paths."""
import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Columns kept from the 54-column BTS export. Every monthly file must have them.
FLIGHT_COLS = [
    "YEAR", "MONTH", "FL_DATE", "OP_UNIQUE_CARRIER", "TAIL_NUM", "ORIGIN", "DEST",
    "CRS_DEP_TIME", "DEP_TIME", "DEP_DELAY", "CRS_ARR_TIME", "ARR_TIME", "ARR_DELAY",
    "ARR_DEL15", "CANCELLED", "CANCELLATION_CODE", "DIVERTED", "DISTANCE",
    "CARRIER_DELAY", "WEATHER_DELAY", "NAS_DELAY", "SECURITY_DELAY", "LATE_AIRCRAFT_DELAY",
]
CAUSE_COLS = ["CARRIER_DELAY", "WEATHER_DELAY", "NAS_DELAY", "SECURITY_DELAY", "LATE_AIRCRAFT_DELAY"]
LOOKUPS = {"L_UNIQUE_CARRIERS.csv": "lkp_carriers", "L_AIRPORT.csv": "lkp_airports",
           "L_CANCELLATION.csv": "lkp_cancellation"}


def load(path=None):
    p = Path(path or os.environ.get("FLIGHTPIPE_CONFIG") or ROOT / "pipeline.toml").resolve()
    cfg = tomllib.loads(p.read_text(encoding="utf-8-sig"))
    cfg["paths"] = {k: (p.parent / v).resolve() for k, v in cfg["paths"].items()}
    if os.environ.get("FLIGHTPIPE_RAW_DIR"):
        cfg["paths"]["raw_dir"] = Path(os.environ["FLIGHTPIPE_RAW_DIR"]).resolve()
    cfg["config_file"] = p
    return cfg
