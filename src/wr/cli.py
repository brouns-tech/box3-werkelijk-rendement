from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from wr.config import load_config, resolve_db_path
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

    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    db_path = resolve_db_path(cfg)

    if args.cmd == "import":
        if args.fresh and db_path.exists():
            db_path.unlink()
        root = args.root or cfg.get("import_root")
        if not root:
            print("import_root not configured", file=sys.stderr)
            return 2
        print(f"Importing from {root}")
        print(f"Database {db_path}")
        stats = run_import(root, db_path, limit=args.limit)
        print(
            "Done: "
            f"seen={stats['seen']} new={stats['new']} duplicate={stats['duplicate']} "
            f"parsed={stats['parsed']} skipped={stats['skipped']} failed={stats['failed']}"
        )
        return 0

    if args.cmd == "recompute":
        recompute(db_path)
        print("Recomputed canonical facts, coverage, and recommendations")
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
            "--",
            "--config",
            cfg.get("_config_path", "config.toml"),
        ]
        return subprocess.call(cmd)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
