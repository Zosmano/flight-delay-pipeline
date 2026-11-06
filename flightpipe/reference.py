"""Extract DOT's published on-time rates from the Air Travel Consumer Report PDFs.

Order of preference for each carrier-month:
  1. Table 1A (operating carrier) of the report that covers that month.
  2. Table 1B of the latest report, which repeats every month of the year by marketing
     carrier with each airline's own flights on a "- NAME" row. Used only for months
     whose own report is not in reference_dir (here, January 2026).
  3. reference/manual_reference.csv: figures typed in from a report that isn't on file.
     Every row there says where it came from, and the run report counts these rows.
"""
import logging
import re
from pathlib import Path

import pandas as pd

log = logging.getLogger("flightpipe.reference")

MONTHS = ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST",
          "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"]
ROW_1A = re.compile(r"^\s*([A-Z][A-Z .&'/-]*?[A-Z])\d?\s*\n\s*(\d+)\s*\n[\s\n]*?(\d{1,3}\.\d)\s*\n", re.M)
TOTAL_1A = re.compile(r"TOTAL AIRPORTS SERVED\s*\n\s*\d+\s*\n[\s\n]*?(\d{1,3}\.\d)")
PERIOD = re.compile(r"(" + "|".join(MONTHS) + r") (20\d\d)")


def pdf_pages(path):
    import pymupdf
    with pymupdf.open(path) as doc:
        return [p.get_text() for p in doc]


def find_page(pages, title):
    return next((t for t in pages if title in t), None)


def parse_table_1a(text, source):
    """Rows (year, month, carrier_name, published_on_time_pct) from the Table 1A page."""
    head = text.split("TABLE 1A.", 1)[1]
    month_name, year = PERIOD.search(head).groups()
    month = MONTHS.index(month_name) + 1
    body = head.split("RANK", 1)[1].split("TOTAL AIRPORTS SERVED", 1)[0] + "\n"
    rows = [(int(year), month, name.strip(), float(pct)) for name, _, pct in ROW_1A.findall(body)]
    total = TOTAL_1A.search(head)
    if total:
        rows.append((int(year), month, "ALL CARRIERS", float(total.group(1))))
    return pd.DataFrame(rows, columns=["year", "month", "carrier_name", "published_on_time_pct"]).assign(
        source_report=source, source_table="Table 1A")


def parse_table_1b(text, source):
    """Own-flight rates by month from Table 1B: a carrier's '- NAME' row if it has branded
    codeshare partners, otherwise its main row (marketing and operating are then the same)."""
    head = text.split("TABLE 1B.", 1)[1]
    year = int(PERIOD.search(head).group(2))
    abbr = [m[:3].title() for m in MONTHS]
    months = [abbr.index(m) + 1
              for m in re.findall(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d\d\b", head)]
    body = head.split("Rank", 1)[1].split("\n1 All U.S.", 1)[0]
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    rows, i = [], 0
    while i < len(lines):
        name = lines[i]
        if not re.match(r"^(- )?[A-Z]", name) or name.startswith("TOTAL"):
            i += 1
            continue
        vals = []
        i += 1
        while i < len(lines) and re.match(r"^(\d+(\.\d)?|N/A)$", lines[i]):
            vals.append(lines[i])
            i += 1
        pcts = vals[0::2] if len(vals) == 2 * (len(months) + 1) else vals
        rows.append((re.sub(r"\d$", "", name).strip(), pcts[:len(months)]))
    out = []
    for k, (name, pcts) in enumerate(rows):
        if name.startswith("- BRANDED"):
            continue
        is_main = not name.startswith("- ")
        has_partners = is_main and k + 1 < len(rows) and rows[k + 1][0].startswith("- ")
        if has_partners:
            continue  # the main row mixes in partners; use the "- NAME" row instead
        carrier = name[2:] if name.startswith("- ") else name
        for m, p in zip(months, pcts):
            if p != "N/A":
                out.append((year, m, carrier, float(p)))
    return pd.DataFrame(out, columns=["year", "month", "carrier_name", "published_on_time_pct"]).assign(
        source_report=source, source_table="Table 1B, own flights")


def build(cfg):
    ref_dir = cfg["paths"]["reference_dir"]
    pdfs = sorted(Path(ref_dir).glob("*.pdf"))
    t1a, t1b = [], []
    for pdf in pdfs:
        pages = pdf_pages(pdf)
        p1a = find_page(pages, "TABLE 1A. OVERALL")
        p1b = find_page(pages, "TABLE 1B. OVERALL")
        if p1a:
            t1a.append(parse_table_1a(p1a, pdf.stem))
        if p1b:
            t1b.append(parse_table_1b(p1b, pdf.stem))
        log.info("read %s: Table 1A %s, Table 1B %s", pdf.name, "found" if p1a else "missing",
                 "found" if p1b else "missing")
    a = pd.concat(t1a, ignore_index=True) if t1a else pd.DataFrame()
    key = ["year", "month", "carrier_name"]
    frames = [a]
    covered = set(map(tuple, a[key].values)) if len(a) else set()
    if t1b:
        latest = max(t1b, key=lambda d: (d.year.max(), d.month.max()))
        b = latest[[tuple(r) not in covered and r[1] not in set(a.month) for r in latest[key].values]]
        frames.append(b)
        covered |= set(map(tuple, b[key].values))
    man_path = cfg["paths"]["manual_reference"]
    if Path(man_path).exists():
        m = pd.read_csv(man_path)
        m = m[[tuple(r) not in covered for r in m[key].values]]
        frames.append(m.assign(source_table=m.get("source_table", "typed in")))
    ref = pd.concat(frames, ignore_index=True)
    ref["method"] = ref.source_table.map(lambda s: "manual" if s.startswith("typed") else "extracted from PDF")
    ref = ref.sort_values(key).reset_index(drop=True)
    if ref.duplicated(key).any():
        raise ValueError("duplicate published figures after merging sources")
    return ref
