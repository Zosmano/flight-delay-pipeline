"""Extract and load: find the monthly BTS files and load them into SQLite incrementally.

Each file is fingerprinted with SHA-256 and recorded in `load_manifest`. On the next run a
file that is already loaded is skipped, a new file is appended, and a file whose contents
changed (BTS revises months) has its old rows replaced. Rows carry a hash of their values
under a unique index, so an exact duplicate row is never stored twice, even across files.
"""
import hashlib
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import FLIGHT_COLS, LOOKUPS

log = logging.getLogger("flightpipe.load")

DDL = f"""
CREATE TABLE IF NOT EXISTS flights (
    {", ".join(c + " NUMERIC" if c not in ("FL_DATE", "OP_UNIQUE_CARRIER", "TAIL_NUM", "ORIGIN", "DEST", "CANCELLATION_CODE") else c + " TEXT" for c in FLIGHT_COLS)},
    OPERATED INTEGER NOT NULL,   -- neither cancelled nor diverted
    ON_TIME INTEGER NOT NULL,    -- DOT definition: operated and arrived < 15 min late
    ROW_HASH INTEGER NOT NULL,
    SOURCE_FILE TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_flights_row ON flights (ROW_HASH);
CREATE INDEX IF NOT EXISTS ix_flights_month_carrier ON flights (MONTH, OP_UNIQUE_CARRIER);
CREATE INDEX IF NOT EXISTS ix_flights_dest ON flights (DEST, OP_UNIQUE_CARRIER, MONTH);
CREATE INDEX IF NOT EXISTS ix_flights_source ON flights (SOURCE_FILE);
CREATE TABLE IF NOT EXISTS load_manifest (
    file TEXT PRIMARY KEY, sha256 TEXT NOT NULL, rows_read INTEGER, rows_inserted INTEGER,
    duplicates INTEGER, periods TEXT, loaded_at TEXT
);
"""
INSERT_COLS = FLIGHT_COLS + ["OPERATED", "ON_TIME", "ROW_HASH", "SOURCE_FILE"]
INSERT_SQL = (f"INSERT OR IGNORE INTO flights ({', '.join(INSERT_COLS)}) "
              f"VALUES ({', '.join('?' * len(INSERT_COLS))})")


def sha256(path, block=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(block):
            h.update(chunk)
    return h.hexdigest()


def read_header(path):
    with open(path, encoding="latin-1") as fh:
        return fh.readline().strip().replace('"', "").split(",")


def discover(raw_dir):
    """Return (flight files, schema problems). A file counts as a monthly flight file if its
    header has FL_DATE; it must then have every column the pipeline needs."""
    files, problems = [], []
    for f in sorted(Path(raw_dir).glob("*.csv")):
        header = read_header(f)
        if "FL_DATE" not in header:
            continue  # lookups and Documentation.csv
        missing = [c for c in FLIGHT_COLS if c not in header]
        if missing:
            problems.append({"file": f.name, "missing_columns": missing})
        else:
            files.append(f)
    return files, problems


def prepare(chunk, source):
    df = chunk[FLIGHT_COLS].copy()
    df["ROW_HASH"] = pd.util.hash_pandas_object(df, index=False).values.view("int64")
    d = pd.to_datetime(df.FL_DATE, format="%m/%d/%Y %I:%M:%S %p", errors="coerce")
    if d.isna().any():
        d = pd.to_datetime(df.FL_DATE, format="mixed")
    df["FL_DATE"] = d.dt.strftime("%Y-%m-%d")
    for c in ("CANCELLED", "DIVERTED"):
        df[c] = df[c].fillna(0).astype(int)
    operated = (df.CANCELLED == 0) & (df.DIVERTED == 0)
    df["OPERATED"] = operated.astype(int)
    # Cancelled and diverted flights stay in the denominator and count as not on time.
    df["ON_TIME"] = (operated & (df.ARR_DEL15 == 0)).astype(int)
    df["SOURCE_FILE"] = source
    df = df[INSERT_COLS].astype(object)
    return df.where(df.notna(), None)


def load_lookups(con, raw_dir):
    for fname, table in LOOKUPS.items():
        p = Path(raw_dir) / fname
        if p.exists():
            pd.read_csv(p, encoding="latin-1", keep_default_na=False, dtype=str).to_sql(
                table, con, if_exists="replace", index=False)
        else:
            log.warning("lookup file %s not found; its quality check will fail", fname)


def run(cfg, full_refresh=False):
    raw, db = cfg["paths"]["raw_dir"], cfg["paths"]["database"]
    db.parent.mkdir(parents=True, exist_ok=True)
    if full_refresh and db.exists():
        db.unlink()
        log.info("full refresh: deleted %s", db.name)
    con = sqlite3.connect(db)
    con.executescript(DDL)
    load_lookups(con, raw)
    files, problems = discover(raw)
    for p in problems:
        log.error("schema: %s is missing %s", p["file"], ", ".join(p["missing_columns"]))
    seen = dict(con.execute("SELECT file, sha256 FROM load_manifest").fetchall())
    summary = []
    for f in files:
        digest = sha256(f)
        if seen.get(f.name) == digest:
            log.info("skip %s (already loaded, unchanged)", f.name)
            summary.append({"file": f.name, "action": "skipped"})
            continue
        if f.name in seen:
            n = con.execute("DELETE FROM flights WHERE SOURCE_FILE = ?", (f.name,)).rowcount
            con.execute("DELETE FROM load_manifest WHERE file = ?", (f.name,))
            log.info("%s changed since last load: removed its %s old rows", f.name, f"{n:,}")
        read = inserted = 0
        periods = set()
        for chunk in pd.read_csv(f, usecols=FLIGHT_COLS, chunksize=cfg["load"]["chunk_rows"],
                                 encoding="latin-1", low_memory=False):
            read += len(chunk)
            periods.update(zip(chunk.YEAR.astype(int), chunk.MONTH.astype(int)))
            before = con.total_changes
            con.executemany(INSERT_SQL, prepare(chunk, f.name).itertuples(index=False, name=None))
            inserted += con.total_changes - before
        con.execute("INSERT INTO load_manifest VALUES (?,?,?,?,?,?,?)",
                    (f.name, digest, read, inserted, read - inserted,
                     ";".join(f"{y}-{m:02d}" for y, m in sorted(periods)),
                     datetime.now(timezone.utc).isoformat(timespec="seconds")))
        con.commit()
        log.info("loaded %s: %s rows, %s duplicates skipped", f.name, f"{inserted:,}", read - inserted)
        summary.append({"file": f.name, "action": "loaded", "rows": inserted, "duplicates": read - inserted})
    con.execute("ANALYZE")
    con.commit()
    con.close()
    return {"files": summary, "schema_problems": problems}
