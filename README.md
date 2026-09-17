# Werkelijk Rendement

Local tool to reconstruct Dutch Box 3 **actual return** (`werkelijk rendement`) from bank/broker PDFs, validate coverage against filed income-tax returns, and compare actual vs fictitious (`forfaitair`) return for fiscal partners.

## Setup

```bash
cd ~/Projects/box3-werkelijk-rendement
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp config.example.toml config.toml
```

Edit `config.toml` (`import_root`, partner names).
## Usage

```bash
wr import                 # recursive PDF import + coverage + recommendations
wr import --root /path
wr dashboard              # Streamlit UI
```

## Notes

- Classification uses PDF **content**, not directory/filename structure.
- Documents are keyed by content SHA-256 (path-independent dedupe).
- Only these document templates are accepted as source data:
  - Official Belastingdienst `Aangifte Inkomstenbelasting` printouts, identified by
    `Eigen kopie, niet opsturen`, `Formulierenversie`, and
    `Burgerservicenummer`. They provide aggregate Box 3 and tax figures only.
  - DEGIRO `Jaaropgave` with portfolio totals; flatex `Steuerbescheinigung` and
    its `Lijst met financiële klanteninstrumenten en klantenfondsen` statement
    dated 31 December. flatex `Rekeninguittreksel` statements are accepted only
    to derive external transfers to or from the linked ING account. DEGIRO and
    flatex are separate sources.
  - ING `Jaaroverzicht`; Rabobank `Financieel Jaaroverzicht`; SNS
    `Jaaroverzicht Betalen, Sparen & Lenen` and `Totaaloverzicht Rekeningen`.
  - Raisin `Financieel Jaaroverzicht`; Revolut `Annual Financial Summary`,
    annual savings statements, and annual account statements.
- This is a positive allowlist: a document is admitted only when it matches one
  of the listed templates. No blacklist of unsupported documents is maintained.
- Account-level Box 3 inventory is derived exclusively from canonical annual
  bank and broker statements, never from an income-tax return.
- After changing the source policy, rebuild with `wr import --fresh` so legacy
  rows from previously accepted templates cannot affect coverage or results.
- For full-year fiscal partners, actual return is computed on the **combined** Box 3 estate, then allocated using the **filed** grondslag split.
- If coverage of the statement-derived Box 3 inventory is incomplete, recommendations are `INDETERMINATE_MISSING_DATA`.
