# Source installation and CLI

Desktop users should use the binaries described in the [README](../README.md).
The CLI remains available for developers and contributors.

## Install from source

Use Python 3.10 or newer. From a repository checkout:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

On Windows, activate the environment with `.venv\Scripts\activate` instead.
See [Contributing](../CONTRIBUTING.md) for development dependencies and tests.

## Try synthetic data

```sh
wr demo
```

This opens a dashboard populated with fictional financial data in a temporary
workspace. It does not import your documents; demo data is removed when the
process stops.

## Import and inspect

```sh
wr import --root /path/to/pdf-statements
wr dashboard
wr recompute
wr export --year 2024
```

Import scans recursively and deduplicates PDFs by content hash. The default
workspace database is `data/wr.sqlite`; the default audit output is
`exports/wr-audit.zip`. The dashboard and CLI share saved taxpayer and institution
settings in `.wr-settings.json` within that workspace. Read the
[user guide](user-guide.md) before relying on a result.

The current directory defines the source-mode workspace. To select another:

```sh
wr --workspace /path/to/workspace dashboard
```

Use `wr dashboard --port 8501` to choose a port, and `wr <command> --help` for
available options. `wr import --fresh` rebuilds imported data while retaining
workspace settings; back up your database before using it.
