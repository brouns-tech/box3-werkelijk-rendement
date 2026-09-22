# Refactoring candidates

This list records structural work that can be completed independently of adding
new statement templates.

## Before a public release

1. **Choose and add a license.** The repository currently has no license file;
   publishing it without one does not grant others permission to reuse or modify
   the code.
2. **Add continuous integration.** Run the test suite on the supported Python
   versions and include a packaging smoke test before accepting pull requests.

## High priority

1. **Replace the parser dispatch chain with a registry.** Classification,
   dispatch, priority, and documentation currently repeat issuer/document-type
   pairs. A typed registry could make one definition authoritative without
   weakening the strict allowlist.
2. **Split the import transaction from progress reporting.** `run_import` prints
   directly and catches broad exceptions. Returning structured per-document
   outcomes would let the CLI and dashboard present errors consistently and make
   failure behavior easier to test.
3. **Introduce versioned database migrations.** `init_db` mixes schema creation
   with ad-hoc column checks. Numbered, transactional migrations would make
   upgrades predictable as the public schema evolves.
4. **Separate tax policy from portfolio arithmetic.** Tax rates and era-specific
   behavior should be explicit policy objects with bounded supported years. The
   current fallback rate for unknown future years can produce unjustified output.

## Medium priority

1. **Use typed configuration.** Validate paths, partner aliases, and IBAN values
   once at the CLI boundary and pass an immutable settings object through the
   pipeline.
2. **Extract shared parser primitives.** Holder parsing, annual-period checks,
   amount extraction, and account normalization recur across institution modules.
   Shared, well-tested helpers would reduce template-specific drift.
3. **Package the dashboard with the Python package.** The CLI currently locates
   `dashboard/app.py` from a source checkout, which is suitable for editable
   installs but not yet robust for a standalone wheel.
4. **Replace float currency arithmetic with decimal values or integer cents.** A
   single money representation would avoid rounding differences across parsers,
   rollups, and exports.

## Completed groundwork

- Configuration is loaded at the application boundary and passed into parsing,
  canonicalization, and recommendation rebuilding instead of being rediscovered
  from the process working directory.
- Running `wr import --root ...` no longer requires a local `config.toml`.
- Dashboard ownership labels come from configuration rather than personal names.
