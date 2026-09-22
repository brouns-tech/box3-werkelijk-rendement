# Contributing

Contributions that add support for more bank and broker statement templates are welcome.

## Add a statement template

1. Add one institution module under `src/wr/parsers/` and export an
   `InstitutionPlugin` named `PLUGIN`.
2. Keep that institution's classification rules, parsers, canonical priorities, option handling, and optional
   post-processing hook in the same module.
3. The registry discovers parser modules automatically. Do not add institution-specific imports, branches, or parameters
   to the registry, CLI, import pipeline, deduplication, portfolio, or recommendation modules.
4. Add synthetic tests for classification, parsing, malformed input, and relevant deduplication or coverage behavior.
   Identifiers must not pass real checksum validation.
5. Add the exact statement name and limitations to
   `docs/supported-documents.md`.

Plugin-specific configuration belongs under an institution namespace:

```toml
[institutions.example]
option_name = "value"
```

The main application passes these values through without knowing their meaning.

Do not commit real statements, extracted text, names, addresses, account numbers, tax identifiers, balances,
`config.toml`, SQLite databases, or audit exports. Synthetic fixtures should use unmistakably fictional names and
reserved example account identifiers.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
```

Keep changes focused and include a regression test for parser fixes. A new parser should fail closed: if the required
identity or annual-period markers are absent, the document must remain unsupported rather than being partially guessed.

Pull requests run the test and wheel smoke-test matrix on Python 3.10 through 3.13. Update tax policies explicitly when
adding support for a new tax year.
