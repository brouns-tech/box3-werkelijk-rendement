# Contributing

Contributions that add support for more bank and broker statement templates are
welcome.

## Add a statement template

1. Add strict content markers to `src/wr/classify.py`. Classification must use
   PDF content, not filenames or directory names, and must avoid matching generic
   terms that can occur in unrelated documents.
2. Add or extend a parser in `src/wr/parsers/`. Return an `AccountYearFact` for
   each account and preserve `None` for values the statement does not establish.
3. Register a new institution or document type in `src/wr/parsers/__init__.py`.
4. Add synthetic, anonymized tests that cover classification, parsing, malformed
   input, and any relevant deduplication or coverage behavior.
5. Add the exact statement name and limitations to the support table in
   `README.md`.

Do not commit real statements, extracted text, names, addresses, account numbers,
tax identifiers, balances, `config.toml`, SQLite databases, or audit exports.
Synthetic fixtures should use unmistakably fictional names and reserved example
account identifiers.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
```

Keep changes focused and include a regression test for parser fixes. A new parser
should fail closed: if the required identity or annual-period markers are absent,
the document must remain unsupported rather than being partially guessed.
