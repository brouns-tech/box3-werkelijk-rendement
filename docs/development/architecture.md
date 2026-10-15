# Package structure

`wr` separates validated data, calculation rules, storage, and application
orchestration. The dashboard and CLI call services rather than importing private
calculation helpers.

| Package | Responsibility |
| --- | --- |
| `models` | Domain objects and validated schemas for facts, tax returns, settings, storage, audit output, and desktop messages |
| `calculations` | Return, coverage, allocation, and tax comparison rules; `service` loads inputs and persists rebuilt results |
| `storage` | SQLite connections, schema migrations, repositories, and row adapters |
| `documents` | Native PDF extraction, positional layout reconstruction, and hashing |
| `parsers` | Institution plugins, plugin discovery, schema selection, and text parsing utilities |
| `importing` | Document classification, scanning, import orchestration, persistence coordination, canonicalization, and reprocessing status |
| `desktop` | Launcher, authenticated control API, instance locking, child processes, server bootstrap, preferences, and synthetic smoke checks |
| `workspace` | Settings file IO, legacy migration, and workspace reset |
| `identities` | Pure name matching and database-backed taxpayer suggestions |

`money`, `messages`, and `i18n` remain focused top-level modules. Audit
assembly lives in `export`; its output schemas live in `models.audit`.

## Household identities

`models.identities.HouseholdSettings` contains immutable, validated identities.
Each person has a stable UUID, a name, and aliases. `TaxpayerIdentity` has role
`taxpayer` and a `TaxpayerPosition` (`primary` or `secondary`); `ChildIdentity`
has role `child` and cannot have a taxpayer position. Names, household roles,
and tax-return positions are not person identifiers.

`identities.matching.resolve_identity` returns the matched identity object or
`None` for unknown, excluded, or ambiguous names. Allocation checks typed roles
and IDs, not string prefixes. Dashboard drafts also use the stable IDs, so
renaming a person or deleting another child keeps drafts associated with the
same people.

Workspace settings version 3 migrates the former `partners` configuration into
`household.identities`, preserving aliases and exclusions and assigning IDs once.
SQLite migration 4 replaces `partner_tax_results` with `taxpayer_tax_results`:
`partner` becomes `taxpayer_position` (`a` → `primary`, `b` → `secondary`), and
`partner_name` becomes `taxpayer_name`. Existing result values are preserved.
Audit format version 2 uses these same column names and values in
`taxpayer_tax_results.csv`. The source-evidence fields `partner_a_name`,
`allocation_a`, and their B counterparts in parsed tax returns still describe
the ordering on the original document, not household identity IDs or roles.

## Dependency direction

Models depend on other models, money helpers, and validation libraries. They do
not discover institution plugins, open databases, or load desktop/UI code.
Institution-specific metadata and option schemas stay in their institution's
parser module.

`parsers._schemas` resolves plugin schemas. `storage.adapters.fact_from_row`
decodes persisted metadata with the registered institution schema before
constructing a `FactRecord`. Calculation functions receive validated records;
they do not accept SQLite rows or deserialize JSON.

Pure calculation modules and `identities.matching` have no persistence or UI
dependencies. `calculations.service` coordinates repositories and calculations.
Import orchestration owns document savepoints, cancellation, progress reporting,
and the order of canonicalization and recalculation. Moving SQL into repositories
does not change those transaction boundaries.

The parser package facade exposes the registry API. Discovery ignores private
modules and the public `base` and `common` support modules, so adding a parser
utility must not accidentally register it as an institution.

## Entry points and verification

The `wr` and `wr-desktop` commands retain their entry points. The desktop also
supports `python -m wr.desktop`, including its `--serve`, `--smoke-test`, and
`--verify-launcher` modes. Packaging verification uses the same typed control
client as the dashboard.

`tests/test_package_boundaries.py` checks model import isolation, calculation
dependency boundaries, and the desktop module entry point. The existing parser,
dashboard, migration, import rollback, calculation, and audit tests protect
behavior across the package moves. Build and install the wheel outside the
checkout when checking distribution packaging.
