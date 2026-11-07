"""Command line: python -m flightpipe [run|load|check|reconcile|analyze] [options]

Exit codes: 0 success, 2 a data-quality check failed, 3 published figures not reproduced,
1 anything else went wrong. A scheduler or CI job can alert on any non-zero code.
"""
import argparse
import logging
import sys
from datetime import datetime, timezone

from . import config, insights, load, paradox, quality, reconcile, report


def setup_logging(cfg, run_id, verbose):
    cfg["paths"]["logs"].mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
    root = logging.getLogger("flightpipe")
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.handlers.clear()
    for h in (logging.StreamHandler(sys.stdout), logging.FileHandler(cfg["paths"]["logs"] / f"{run_id}.log", encoding="utf-8")):
        h.setFormatter(fmt)
        root.addHandler(h)
    return root


def main(argv=None):
    ap = argparse.ArgumentParser(prog="flightpipe", description=__doc__.splitlines()[0])
    ap.add_argument("stage", nargs="?", default="run", choices=["run", "load", "check", "reconcile", "analyze"],
                    help="run = every stage; the others stop after that stage (analyze = paradox and insights)")
    ap.add_argument("--config", help="path to pipeline.toml")
    ap.add_argument("--full-refresh", action="store_true", help="rebuild the database from scratch")
    ap.add_argument("--strict", action="store_true", help="also stop the run if a flag check finds rows")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    cfg = config.load(args.config)
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    log = setup_logging(cfg, run_id, args.verbose)
    log.info("run %s, config %s, raw files in %s", run_id, cfg["config_file"].name, cfg["paths"]["raw_dir"])
    stages = ["load", "check", "reconcile", "analyze"]
    upto = stages.index(args.stage) if args.stage != "run" else len(stages) - 1
    rec = par = ins = None
    code = 0
    try:
        load_result = load.run(cfg, full_refresh=args.full_refresh)
        dq = quality.run(cfg, run_id, load_result)
        failed = dq.status.eq("fail") | (args.strict & dq.status.eq("flagged"))
        if failed.any():
            code = 2
            log.error("stopping: %d data-quality check(s) failed", int(failed.sum()))
        if code == 0 and upto >= 2:
            rec = reconcile.run(cfg, run_id)
            if not rec.match.all():
                code = 3
        if code == 0 and upto >= 3:
            par = paradox.run(cfg, run_id)
            ins = insights.run(cfg, run_id)
        status = {0: "success", 2: "failed data-quality checks", 3: "did not reproduce published figures"}[code]
        report.write(cfg, run_id, started, load_result, dq, rec, par, status, ins)
        log.info("report: %s", cfg["paths"]["outputs"] / "run_report.md")
    except Exception:
        log.exception("run %s crashed", run_id)
        return 1
    log.info("finished with exit code %d", code)
    return code


if __name__ == "__main__":
    sys.exit(main())
