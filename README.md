# Werkelijk Rendement

Werkelijk Rendement is a local Python tool for reconstructing Dutch Box 3 actual
return (`werkelijk rendement`) from annual bank and broker statements. It compares
that result with the fictitious return (`forfaitair rendement`) reported in an
income-tax return and can produce an auditable ZIP export.

> [!WARNING]
> This project is an analysis aid, not tax or financial advice. Verify its output
> against the source documents and current Belastingdienst guidance before filing.

## Supported documents

Support is deliberately allowlisted: a PDF is imported only when its extracted
text matches a known template. Renamed files and arbitrary folder layouts are
fine; unsupported templates are skipped.

| Institution | Supported PDF statement | Use and limitations |
| --- | --- | --- |
| Belastingdienst | `Aangifte Inkomstenbelasting` copy containing `Eigen kopie, niet opsturen`, `Formulierenversie`, and `Burgerservicenummer`; supported final-assessment layout | Supplies aggregate Box 3 and filed tax figures, never the account inventory. |
| DEGIRO | `Jaaropgave` / `Jaaroverzicht` containing opening and closing portfolio totals | Supplies portfolio balances, deposits, withdrawals, and return components. |
| flatex | `Lijst met financiële klanteninstrumenten en klantenfondsen` dated 31 December | Supplies the year-end securities-and-cash inventory. Adjacent years are needed to derive a full-year value change. |
| flatex | `Rekeninguittreksel` | Used only for external transfers involving the configured linked bank account. Cash sweeps are excluded. |
| flatex | `Steuerbescheinigung` | Accepted as supplementary legacy income data; it is not a complete portfolio inventory. |
| ING | `Jaaroverzicht` for ING payment, savings, and credit-card products | Supplies account balances and reported interest. |
| Rabobank | `Financieel Jaaroverzicht` | Supplies account balances and reported interest. |
| SNS | `Jaaroverzicht Betalen, Sparen & Lenen`, `Financieel overzicht`, and `Totaaloverzicht Rekeningen` | The total overview supplies balances; savings accounts without a reported interest figure remain incomplete. |
| Raisin | `Raisin Financieel Jaaroverzicht` | Supplies savings-product balances, interest, and withholding tax. |
| Revolut | `Annual Financial Summary` | Supplies annual account data. |
| Revolut | Annual Flexible Cash Funds savings statement | Supplies earned return for the savings product. |
| Revolut | Personal current-account statement covering 1 January through 31 December | Supplies balances and flows. Revolut Business statements are not supported. |

The PDF must contain extractable text. Image-only scans are not OCRed. CSV files,
transaction exports, interim statements (except the listed flatex statements),
and templates from other banks or brokers are currently unsupported. Support for
additional cases is welcome through pull requests; see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Requirements

- Python 3.10 or newer
- Optional but recommended: Poppler's `pdftotext` executable for more reliable
  layout-preserving extraction. The tool falls back to `pypdf`.

## Installation

From a checkout of this repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

The shortest usable invocation needs no configuration file:

```bash
wr import --root /path/to/your/pdf-statements
wr dashboard
```

By default, the SQLite database is written to `data/wr.sqlite` under the current
directory.

## Configuration

Copy the example only when you need persistent paths, partner aliases, or flatex
transfer matching:

```bash
cp config.example.toml config.toml
```

Then edit the values for your environment. Relative `db_path` values are resolved
relative to the configuration file. Pass a different file with
`wr --config /path/to/config.toml <command>`.

The `accounts.flatex_linked_account` setting is important when importing flatex
account statements: only transfers to or from that IBAN are treated as external
portfolio flows. Partner names and aliases improve matching when statement and
tax-return name formats differ.

## Commands

```bash
wr import --root /path/to/pdfs  # recursively import supported PDFs
wr import --fresh               # rebuild the configured database from scratch
wr recompute                    # recompute existing imported facts
wr dashboard --port 8501        # launch the local Streamlit dashboard
wr export --year 2024           # write exports/wr-audit.zip
```

Run `wr <command> --help` for all options. After changing source or parser rules,
use `wr import --fresh` so previously admitted rows cannot affect the result.

## Data and privacy

Processing is local, but the SQLite database contains source paths, extracted PDF
text excerpts, account identifiers, holder names, balances, and tax figures. Audit
exports can also contain identifying financial data. `config.toml`, the default
`data/` directory, SQLite files, and `exports/` are ignored by Git; rSAMw files
before sharing them.

Documents are deduplicated by content SHA-256. For full-year fiscal partners, the
combined Box 3 return is allocated using the filed taxable-base split. Incomplete
statement coverage produces `INDETERMINATE_MISSING_DATA` rather than a definitive
recommendation.

## Development

```bash
python -m pip install -e '.[dev]'
pytest
```

Known structural improvements are tracked in
[docs/refactoring.md](docs/refactoring.md).
