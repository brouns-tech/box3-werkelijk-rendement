from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from wr.config import load_config, resolve_db_path
from wr.export import write_audit_export
from wr.import_pipeline import recompute, run_import


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

    p_export = sub.add_parser("export", help="Export an auditable ZIP bundle")
    p_export.add_argument(
        "--output", default="exports/wr-audit.zip", help="Destination ZIP path"
    )
    p_export.add_argument(
        "--year", type=int, action="append", help="Tax year to include (repeatable)"
    )

    args = parser.parse_args(argv)
    try:
        cfg = load_config(args.config)
    except FileNotFoundError as exc:
        parser.error(str(exc))
    db_path = resolve_db_path(cfg)
    partner_config = cfg.get("partners", {})
    flatex_linked_account = cfg.get("accounts", {}).get("flatex_linked_account")

    if args.cmd == "import":
        if args.fresh and db_path.exists():
            db_path.unlink()
        root = args.root or cfg.get("import_root")
        if not root:
            print("Provide --root or set import_root in config.toml", file=sys.stderr)
            return 2
        if not Path(root).is_dir():
            print(f"Import root is not a directory: {root}", file=sys.stderr)
            return 2
        print(f"Importing from {root}")
        print(f"Database {db_path}")
        stats = run_import(
            root,
            db_path,
            limit=args.limit,
            partner_config=partner_config,
            flatex_linked_account=flatex_linked_account,
        )
        print(
            "Done: "
            f"seen={stats['seen']} new={stats['new']} duplicate={stats['duplicate']} "
            f"parsed={stats['parsed']} skipped={stats['skipped']} failed={stats['failed']}"
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
        app = Path(__file__).resolve().parents[2] / "dashboard" / "app.py"
        if not app.exists():
            app = Path(cfg["_project_root"]) / "dashboard" / "app.py"
        cmd = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app),
            "--server.port",
            str(args.port),
        ]
        if cfg.get("_config_path"):
            cmd.extend(["--", "--config", cfg["_config_path"]])
        return subprocess.call(cmd)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
