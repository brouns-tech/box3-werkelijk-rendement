# Werkelijk Rendement

Local tool to reconstruct Dutch Box 3 **actual return** (`werkelijk rendement`) from bank/broker PDFs, validate coverage against filed income-tax returns, and compare actual vs fictitious (`forfaitair`) return for fiscal partners.

## Setup

```bash
cd ~/Projects/box3-werkelijk-rendement
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Configure `config.toml` (`import_root`, partner names).

## Usage

```bash
wr import                 # recursive PDF import + coverage + recommendations
wr import --root /path
wr dashboard              # Streamlit UI
```

## Notes

- Classification uses PDF **content**, not directory/filename structure.
- Documents are keyed by content SHA-256 (path-independent dedupe).
- For full-year fiscal partners, actual return is computed on the **combined** Box 3 estate, then allocated using the **filed** grondslag split.
- If coverage of declared Box 3 assets is incomplete, recommendations are `INDETERMINATE_MISSING_DATA`.
