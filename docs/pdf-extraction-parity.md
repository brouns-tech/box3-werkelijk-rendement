# PDF extraction parity

## Decision

Both source CLI and desktop builds use pinned `pypdfium2==5.14.0`. PDFium ships
inside the Python wheel and frozen application, with its dependency license texts.
No financial documents are sent outside the computer. Poppler remains useful as
an independent development reference, but is not a runtime dependency.

The previous desktop used plain pypdf extraction while the CLI preferred Poppler
`-layout`. Content-stream order can put form labels before their values and lose
table columns. This caused incorrect Revolut holder names and incomplete SNS and
flatex imports, including missing financial facts.

The shared layout helper groups PDFium words by baseline and horizontal position.
It retains wide table gaps and line boundaries, normalizes ordinary word spaces,
and excludes vertical margin annotations. Predominantly rotated body text is
reported as unsupported rather than accepted as a partial extraction. PDFium
calls run under a process-wide lock because the native library is not thread-safe.
Native document, page, and text handles close deterministically.

Parser changes accommodate horizontal spacing without weakening institution
identification. Numeric fields cannot absorb page-footer digits; missing taxable
bases cannot read a following heading number. SNS holder tails stay on the IBAN
line. Revolut name fields require values on their own label row. Tax rules and
calculation policies are unchanged.

## Existing workspaces

Schema migration 3 adds `documents.processing_profile`. The profile versions the
layout algorithm and native dependency. A scan reprocesses older parsed records
instead of treating them as duplicates. It replaces all previous facts and tax
returns belonging to that document, including obsolete accounts and years.
Failed extraction/persistence leaves a failed document record and no stale or
partially written financial records. Retry and cancellation remain supported.
Original files, content hashes, initial provenance, and workspace profiles remain
intact. Current successful imports deduplicate normally on subsequent scans.

The dashboard withholds the comparison while older parsed documents still need
refreshing. Audit manifests report the pending count and processing profiles;
source-fact CSV rows include the extractor profile. Synthetic demo records are
explicitly identified separately.

## Validation

A local read-only comparison covered 77 supported PDFs across the eight supported
institutions. With the same parsers, the shared backend and Poppler produced
identical complete parsed results: 91 account facts and all tax-return fields.
No financial documents, extracted private text, or real fixture identifiers were
added to the repository. This is a bounded compatibility check, not evidence that
all possible layouts work.

Synthetic regression PDFs deliberately write labels and values in separate
content-stream columns. Tests cover Revolut holder names and values, SNS joint and
child accounts, obsolete record replacement, failure rollback, versioned
migration, repeat scans, missing values, and page-footer contamination. Frozen
smoke tests include column-first PDFs as well as all institution fixtures.

Tests run from temporary workspaces and restrict SQLite access to temporary files.
This prevents a missing workspace argument from importing test fixtures into a
maintainer's real database or changing their settings. Packaged validation also
uses synthetic data and isolated storage with no Python/Poppler on PATH.

References: [PDFium Python API](https://pypdfium2.readthedocs.io/en/stable/python_api.html)
and [distribution and license information](https://github.com/pypdfium2-team/pypdfium2).
