from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
import tempfile
from pathlib import Path

from wr.config import load_config, resolve_db_path
from wr.export import write_audit_export
from wr.import_pipeline import DocumentImportOutcome, ImportStatus, recompute, run_import


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wr", description="Werkelijk rendement Box 3 toolkit")
    parser.add_argument("--config", help="Path to config.toml")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_import = sub.add_parser("import", help="Import PDFs recursively and rebuild analysis")
    p_import.add_argument("--root", help="Override import_root")
    p_import.add_argument("--limit", type=int, help="Limit number of PDFs (debug)")
    p_import.add_argument("--fresh", action="store_true", help="Delete DB before import")

    sub.add_parser("recompute", help="Re-run dedupe/coverage/recommendations on existing DB")

    p_dash = sub.add_parser("dashboard", help="Launch Streamlit dashboard")
    p_dash.add_argument("--port", type=int, default=8501)

    p_demo = sub.add_parser("demo", help="Launch a dashboard with synthetic example data")
    p_demo.add_argument("--port", type=int, default=8501)

    p_export = sub.add_parser("export", help="Export an auditable ZIP bundle")
    p_export.add_argument(
        "--output", default="exports/wr-audit.zip", help="Destination ZIP path"
    )
    p_export.add_argument(
        "--year", type=int, action="append", help="Tax year to include (repeatable)"
    )

    args = parser.parse_args(argv)
    if args.cmd == "demo":
        from wr.demo import create_demo_workspace

        with tempfile.TemporaryDirectory(prefix="werkelijk-rendement-demo-") as directory:
            config_path = create_demo_workspace(directory)
            print("Opening dashboard with synthetic example data")
            return _launch_dashboard(config_path, args.port)

    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
    db_path = resolve_db_path(cfg)
    partner_config = cfg.partners
    flatex_linked_account = cfg.accounts.flatex_linked_account

    if args.cmd == "import":
        if args.fresh and db_path.exists():
            db_path.unlink()
        root = Path(args.root) if args.root else cfg.import_root
        if not root:
            print("Provide --root or set import_root in config.toml", file=sys.stderr)
            return 2
        if not Path(root).is_dir():
            print(f"Import root is not a directory: {root}", file=sys.stderr)
            return 2
        print(f"Importing from {root}")
        print(f"Database {db_path}")
        report = run_import(
            root,
            db_path,
            limit=args.limit,
            partner_config=partner_config,
            flatex_linked_account=flatex_linked_account,
            progress=_print_import_outcome,
        )
        print(
            "Done: "
            f"seen={report.seen} new={report.new} duplicate={report.duplicate} "
            f"parsed={report.parsed} skipped={report.skipped} failed={report.failed}"
        )
        return 0

    if args.cmd == "recompute":
        recompute(
            db_path,
            partner_config=partner_config,
            flatex_linked_account=flatex_linked_account,
        )
        print("Recomputed canonical facts, coverage, and recommendations")
        return 0

    if args.cmd == "export":
        if not db_path.exists():
            print(f"Database not found: {db_path}", file=sys.stderr)
            return 2
        destination = write_audit_export(db_path, args.output, args.year)
        print(f"Audit export written to {destination.resolve()}")
        return 0

    if args.cmd == "dashboard":
        return _launch_dashboard(cfg.config_path, args.port)

    return 1


def _launch_dashboard(config_path: Path | None, port: int) -> int:
    app_module = importlib.import_module("dashboard.app")
    app = Path(app_module.__file__).resolve()
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app),
        "--server.port",
        str(port),
    ]
    if config_path:
        cmd.extend(["--", "--config", str(config_path)])
    try:
        return subprocess.call(cmd)
    except KeyboardInterrupt:
        return 130


def _print_import_outcome(outcome: DocumentImportOutcome) -> None:
    prefix = f"[{outcome.index}/{outcome.total}]"
    if outcome.status is ImportStatus.PARSED:
        source = f"{outcome.issuer}/{outcome.doc_type}"
        print(f"{prefix} parsed {source} {outcome.tax_year or 'unknown'} {outcome.path}")
    elif outcome.error:
        print(f"{prefix} {outcome.status.value} {outcome.path}: {outcome.error}")
    else:
        print(f"{prefix} {outcome.status.value} {outcome.path}")


if __name__ == "__main__":
    raise SystemExit(main())
