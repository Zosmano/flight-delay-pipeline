"""Step 1: load the raw BTS monthly CSVs into SQLite and record data-quality checks.

Reads every CSV in data/raw/ that carries the BTS on-time columns (lookup tables
and Documentation.csv are skipped), streams it in chunks so memory stays low,
casts types, drops exact duplicate rows, adds derived fields and writes one
`flights` table plus lookup tables.
"""
import sqlite3
import sys

import pandas as pd

from config import (CANCELLATION_REASONS, CARRIERS, DB_PATH, KEEP_COLS,
                    RAW_DIR, CAUSE_COLS)

CHUNK = 250_000


def find_monthly_files(raw_dir):
    files = []
    for f in sorted(raw_dir.glob("*.csv")):
        with open(f, encoding="latin-1") as fh:
            header = fh.readline().replace('"', "").strip().split(",")
        if set(KEEP_COLS).issubset(header):
            files.append(f)
    if not files:
        sys.exit(f"No BTS on-time CSVs found in {raw_dir}. See README, step 1.")
    return files


def clean_chunk(df):
    df = df.copy()
    df["FL_DATE"] = pd.to_datetime(df["FL_DATE"], format="mixed").dt.strftime("%Y-%m-%d")
    for c in ["CANCELLED", "DIVERTED"]:
        df[c] = df[c].fillna(0).astype(int)
    operated = (df.CANCELLED == 0) & (df.DIVERTED == 0)
    # DOT definition: on time = operated and arrived less than 15 minutes late.
    # Cancelled and diverted flights stay in the denominator as not on time.
    df["ON_TIME"] = (operated & (df.ARR_DEL15 == 0)).astype(int)
    df["OPERATED"] = operated.astype(int)
    # Scheduled departure hour (CRS_DEP_TIME is hhmm local time).
    df["DEP_HOUR"] = (df.CRS_DEP_TIME // 100).clip(upper=23).astype(int)
    df["SEVERE_DELAY"] = (operated & (df.ARR_DELAY >= 180)).astype(int)
    return df


def run():
    files = find_monthly_files(RAW_DIR)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)

    file_log = []
    seen = set()          # row hashes, to drop exact duplicates across files
    dupes = 0
    for f in files:
        rows_in = rows_out = 0
        for chunk in pd.read_csv(f, usecols=KEEP_COLS, chunksize=CHUNK,
                                 encoding="latin-1", low_memory=False):
            rows_in += len(chunk)
            h = pd.util.hash_pandas_object(chunk, index=False)
            keep = ~h.isin(seen) & ~h.duplicated()
            dupes += int((~keep).sum())
            seen.update(h[keep].tolist())
            chunk = clean_chunk(chunk[keep.values])
            chunk.to_sql("flights", con, if_exists="append", index=False)
            rows_out += len(chunk)
        file_log.append({"file": f.name, "rows_read": rows_in, "rows_loaded": rows_out})
        print(f"  loaded {f.name}: {rows_out:,} rows")

    pd.DataFrame([{"code": k, "carrier_name": v[0], "atcr_name": v[1]}
                  for k, v in CARRIERS.items()]).to_sql("carriers", con, index=False)
    pd.DataFrame([{"code": k, "reason": v} for k, v in CANCELLATION_REASONS.items()]
                 ).to_sql("cancellation_reasons", con, index=False)

    cur = con.cursor()
    for idx in ["MONTH, OP_UNIQUE_CARRIER", "ORIGIN", "DEST", "DEP_HOUR"]:
        name = "ix_" + idx.replace(", ", "_").lower()
        cur.execute(f"CREATE INDEX {name} ON flights ({idx})")
    con.commit()

    checks = quality_checks(con)
    con.close()
    return file_log, dupes, checks


def quality_checks(con):
    """Return (check, value, expectation) rows describing the loaded table."""
    q = lambda sql: con.execute(sql).fetchone()[0]
    cause_sum = " + ".join(f"COALESCE({c},0)" for c in CAUSE_COLS)
    return [
        ("Total rows loaded", q("SELECT COUNT(*) FROM flights"), "matches sum of files"),
        ("Distinct carriers", q("SELECT COUNT(DISTINCT OP_UNIQUE_CARRIER) FROM flights"), "13 or fewer"),
        ("Carrier codes missing from lookup",
         q("SELECT COUNT(DISTINCT OP_UNIQUE_CARRIER) FROM flights WHERE OP_UNIQUE_CARRIER NOT IN (SELECT code FROM carriers)"), "0"),
        ("Distinct airports (origin)", q("SELECT COUNT(DISTINCT ORIGIN) FROM flights"), "informational"),
        ("Cancelled flights", q("SELECT SUM(CANCELLED) FROM flights"), "informational"),
        ("Diverted flights", q("SELECT SUM(DIVERTED) FROM flights"), "informational"),
        ("Cancelled flights without a reason code",
         q("SELECT COUNT(*) FROM flights WHERE CANCELLED=1 AND CANCELLATION_CODE IS NULL"), "0"),
        ("Cancelled flights with an arrival delay recorded",
         q("SELECT COUNT(*) FROM flights WHERE CANCELLED=1 AND ARR_DELAY IS NOT NULL"), "0"),
        ("Operated flights missing arrival delay",
         q("SELECT COUNT(*) FROM flights WHERE OPERATED=1 AND ARR_DELAY IS NULL"), "0"),
        ("Flights 15+ min late whose cause minutes do not sum to the arrival delay",
         q(f"SELECT COUNT(*) FROM flights WHERE OPERATED=1 AND ARR_DELAY>=15 AND ({cause_sum}) <> ARR_DELAY"),
         "near 0; flagged, not dropped (BTS reports causes for delays of 15+ min)"),
        ("Rows missing tail number", q("SELECT COUNT(*) FROM flights WHERE TAIL_NUM IS NULL"),
         "informational (mostly cancellations)"),
        ("Scheduled departure time outside 0001-2359",
         q("SELECT COUNT(*) FROM flights WHERE CRS_DEP_TIME < 1 OR CRS_DEP_TIME > 2359"), "0"),
    ]


if __name__ == "__main__":
    run()
