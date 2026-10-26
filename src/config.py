"""Shared paths, column lists and lookup values for the pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "flights.db"
SQL_DIR = ROOT / "sql"
REFERENCE_DIR = ROOT / "reference"
TABLES_DIR = ROOT / "outputs" / "tables"
FIGURES_DIR = ROOT / "outputs" / "figures"
REPORT_PATH = ROOT / "outputs" / "data_quality_report.md"

# Fields kept from the 54-column BTS export.
KEEP_COLS = [
    "FL_DATE", "MONTH", "DAY_OF_WEEK", "OP_UNIQUE_CARRIER", "TAIL_NUM",
    "ORIGIN", "ORIGIN_CITY_NAME", "ORIGIN_STATE_ABR",
    "DEST", "DEST_CITY_NAME", "DEST_STATE_ABR",
    "CRS_DEP_TIME", "DEP_TIME", "DEP_DELAY",
    "CRS_ARR_TIME", "ARR_TIME", "ARR_DELAY", "ARR_DEL15",
    "CANCELLED", "CANCELLATION_CODE", "DIVERTED", "DISTANCE",
    "CARRIER_DELAY", "WEATHER_DELAY", "NAS_DELAY", "SECURITY_DELAY",
    "LATE_AIRCRAFT_DELAY",
]

CAUSE_COLS = ["CARRIER_DELAY", "WEATHER_DELAY", "NAS_DELAY",
              "SECURITY_DELAY", "LATE_AIRCRAFT_DELAY"]

# BTS carrier codes -> names (matches the BTS L_UNIQUE_CARRIERS lookup) and the
# names DOT prints in the Air Travel Consumer Report, used for validation.
CARRIERS = {
    "AA": ("American Airlines", "AMERICAN AIRLINES"),
    "AS": ("Alaska Airlines", "ALASKA AIRLINES"),
    "B6": ("JetBlue Airways", "JETBLUE AIRWAYS"),
    "DL": ("Delta Air Lines", "DELTA AIR LINES"),
    "F9": ("Frontier Airlines", "FRONTIER AIRLINES"),
    "G4": ("Allegiant Air", "ALLEGIANT AIR"),
    "MQ": ("Envoy Air", "ENVOY AIR"),
    "NK": ("Spirit Airlines", "SPIRIT AIRLINES"),
    "OH": ("PSA Airlines", "PSA AIRLINES"),
    "OO": ("SkyWest Airlines", "SKYWEST AIRLINES"),
    "UA": ("United Airlines", "UNITED AIRLINES"),
    "WN": ("Southwest Airlines", "SOUTHWEST AIRLINES"),
    "YX": ("Republic Airways", "REPUBLIC AIRWAYS"),
}

CANCELLATION_REASONS = {"A": "Carrier", "B": "Weather",
                        "C": "National Air System", "D": "Security"}

MONTH_NAMES = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
               7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}
