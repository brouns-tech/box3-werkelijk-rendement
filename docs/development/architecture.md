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
| `importing` | Document classification, scanning, import orchestration, persistence coordination, and reprocessing status |
| `desktop` | Launcher, authenticated control API, instance locking, child processes, server bootstrap, preferences, and installed-application diagnostics |
| `reconciliation` | Pure evidence merging and service coordination of institution-specific reconciliation rules |
| `workspace` | JSON settings IO, schema upgrades, and workspace reset |
| `identities` | Pure name matching and database-backed taxpayer suggestions |

`money`, `messages`, and `i18n` remain focused top-level modules. Audit
assembly lives in `export`; its output schemas live in `models.audit`.

## Application configuration

`wr.config` is the single source for application defaults: the settings filename,
desktop data-directory name, database filenames, CLI dashboard port, export path,
and desktop state/log filenames. It uses only the standard library, so models
can share these defaults without importing application services. Platform data
roots are resolved by `desktop.storage` at runtime, honoring `LOCALAPPDATA` or
`XDG_DATA_HOME`.

Per-workspace overrides (database path, import folder, household, and institution
options) remain in `.wr-settings.json`, validated by `models.settings` and saved
atomically by `workspace.settings`. CLI workspaces default to `data/wr.sqlite`;
desktop workspaces default to `wr.sqlite` in the application data directory.
Earlier JSON versions upgrade automatically. Retired TOML application settings
are not loaded or migrated; use the dashboard to configure a workspace.
Static release artifact names and package metadata remain build-time contracts,
not user settings.

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
Audit format version 3 retains these same column names and values in
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
and the order of reconciliation and recalculation. Moving SQL into repositories
does not change those transaction boundaries.

The parser package facade exposes the registry API. Discovery ignores private
modules and the public `base` and `common` support modules, so adding a parser
utility must not accidentally register it as an institution.

## Observations and reconciliation

The pipeline is `scan → hash/deduplicate → extract → classify → parse → persist
observations → reconcile → calculate coverage and recommendations`.

`account_year_facts` contains document observations, including any return
components derived by the parser from that single document. Reconciliation never
updates these rows. Reprocessing replaces a document's complete observations;
it also invalidates derived state before rebuilding it.

`reconciliation.engine` groups observations by year, issuer, and normalized
account key. It reconciles each monetary field separately: complementary values
fill gaps, matching values retain all supporting references, and disagreement
leaves the field unresolved. Amounts are compared at cent precision. Holder
order/case differences are normalized, but different holder sets, ownership,
currency, incompatible gain methods, and Box 3 treatment remain explicit conflicts.
An explicit market gain can be combined with separately reported net interest;
the derived method explains why those two source methods are compatible.
Unknown values are absence of evidence, not votes for zero.

Each `ReconciledFact` has typed `FieldEvidence` entries with a status
(`missing`, `single_source`, `agreement`, `conflict`, or `derived`), source
observation IDs, document hashes, original field values, and derivation rules.
These statuses describe support, not calibrated probabilities: agreement across
different PDF hashes does not prove independent corroboration. Identical PDF
hashes do not create extra support. Display labels and descriptive metadata are
not financial authority. Holder inference is limited to the same account/year;
there is no issuer-wide or cross-year ownership fallback.

Institution plugins may provide a pure `reconcile(observations, options)` hook,
not a database-mutating postprocessor. Flatex distinguishes portfolio valuations
from cash statements, reconciles copies of each numbered statement before
summing external flows, and traces opening values to the prior year's inventory
or an opening statement. Cash-only balances are not treated as portfolio
returns. SNS can improve display labels across years without modifying source
evidence. There is no document-priority winner selection.

The service persists validated results separately in `reconciled_facts`, with
stable IDs for retained account/year groups and atomic replacement. Calculations,
the account overview, and audit assets consume these derived results, not a
selected source row. Unresolved conflicts block that account's return and keep
coverage incomplete. The dashboard exposes the underlying evidence in an
expandable JSON view.

Audit format 3 adds `reconciled_facts.json`. `assets.csv` contains derived
account-year results; `source_facts.csv` contains original observations and links
to the derived results, including prior-year observations used in derivations.
Source observations are never directly included in annual totals.

SQLite migration 6 removes the canonical flag and adds the derived-results
table. Earlier versions modified source observations during postprocessing, so
their original values cannot reliably be reconstructed from the database.
The migration retains those rows for safety, invalidates their trust marker and
old calculations, and requires re-importing the PDFs before using their evidence
again. A matching extraction profile does not bypass this requirement. Back up
existing workspaces before upgrading; the migration runs when the workspace
database is opened.

## Entry points and verification

The `wr` and `wr-desktop` commands retain their entry points. The desktop also
supports `python -m wr.desktop`, including its `--serve`, `--smoke-test`, and
`--verify-launcher` modes. Packaging verification uses the same typed control
client as the dashboard.

`desktop.selfcheck` implements the packaged `--smoke-test` diagnostic: one
synthetic PDF exercises native extraction, import, calculation, and audit export.
It reports failures with exceptions rather than assertions, so checks remain
active under optimized Python. Release verification retains the same
`smoke-result.json`, `smoke-error.log`, and `audit.zip` artifact contract.
Comprehensive institution samples and PDF-generation helpers live exclusively
under `tests/support`; detailed extraction and multi-institution integration
checks run in pytest, not in the installed application.

`tests/test_package_boundaries.py` checks model import isolation, calculation
dependency boundaries, and the desktop module entry point. The existing parser,
dashboard, migration, import rollback, calculation, and audit tests protect
behavior across the package moves. Build and install the wheel outside the
checkout when checking distribution packaging.
