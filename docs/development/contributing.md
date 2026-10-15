# Contributing

See [package structure and dependency boundaries](architecture.md) before adding
new modules or moving shared functionality.

Contributions that add support for more bank and broker statement templates are welcome.

## Language

Write repository documentation, contribution guides, and release notes in English.
Keep original Dutch tax terms, document titles, and quoted interface labels where
needed for accuracy. The application interface may support Dutch and English;
documentation language does not determine the interface language.

Application translations live in `src/wr/messages.py`. Add a named constant to
`Messages` with a frozen `Message(en=..., nl=...)`, then use
`translator(language)(Messages.SETTINGS_SAVED)` at the call site. For text with
parameters, use `MessageTemplate` and add a method with typed, keyword-only
parameters to `Translator` in `src/wr/i18n.py`, such as
`translator(language).child(number=1)`. Keep formatting placeholders identical
between languages; template construction validates this. Dashboard controls use
`ui_translator()` to get the current session's translator. Institution setting
labels and help accept message objects or literal plugin-owned text.
Pass the session's language explicitly; do not
change the process-wide locale or translate stored financial facts and policy
identifiers. Add translations for new UI messages and stable status labels.
`tests/test_i18n.py` checks catalog coverage, placeholders, language switching,
preference persistence, and preservation of financial data.

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
   [document compatibility matrix](../reference/supported-documents.md).

Plugins declare UI settings using `InstitutionPlugin.settings_fields`:

```python
settings_fields=(InstitutionSetting("option_name", "Option label", "Help text"),)
```

The Settings tab renders these fields and persists their values under the
institution namespace. The main application passes the values through without
knowing their meaning.

Plugins can declare `options_model` and `metadata_model` on `InstitutionPlugin`.
Use Pydantic models extending `InstitutionSettings` and `FactMetadata`, respectively,
and keep institution-specific fields in the institution module. Parsers receive a
validated options object; parsed facts expose metadata through attributes, such as
`fact.extra.box3`. Nested evidence and security positions should also be models.
Institution options preserve unrecognized JSON extension fields for compatibility.
Fact metadata rejects unknown fields and invalid types rather than silently
ignoring evidence used in calculations.

SQLite and JSON are validation boundaries. Use `FactRecord`, `PortfolioRecord`,
and `TaxReturnRecord` for calculation inputs and typed export records for audit
output. Convert to dictionaries only when binding SQL parameters or writing
CSV/JSON. `insert_facts` accepts parsed `AccountYearFact` objects directly.
Models live under `wr.models`; use `wr.storage.adapters.fact_from_row` to decode
stored facts with their institution-specific metadata schema. Calculation
functions under `wr.calculations` receive validated records directly.
Document updates validate their column names and distinguish omitted fields from
explicit null values. Keep ordinary lookup tables and translated display columns
as dictionaries; they do not represent fixed record schemas.

Do not commit real statements, extracted text, names, addresses, account numbers, tax identifiers, balances,
`.wr-settings.json`, retired configuration files, SQLite databases, or audit exports. Synthetic fixtures should use unmistakably fictional names and
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
