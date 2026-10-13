# Windows delivery assessment and Phase 1 implementation

## Baseline

The repository already separates classification, deterministic institution plugins,
canonicalization, portfolio coverage, tax comparison, and ZIP audit export. Eight
institution plugins are discovered dynamically. Fiscal-partner assessment and
unsupported-year / incomplete-evidence decisions already exist. The dashboard is
read-only; importing and configuring it previously required CLI use. The baseline
suite passed: 60 tests, including parser, partner, coverage, money, policy,
migration, demo, export, and plugin cases. No calculation or tax-policy changes
are needed for packaging.

Important gaps: no executable lifecycle, native folder picker, packaged-resource
tests, PDF extraction regression fixtures, or Windows CI. Database defaults were
relative to the CLI workspace. SQLite connections in imports and dashboard reruns
were not explicitly closed. The plugin registry used a physical directory rather
than its package path, which is unsuitable for some frozen importers.

## Delivery decision

Use PyInstaller one-folder, CPython 3.13.5 x64, the existing Streamlit dashboard,
and a small Tkinter supervisor. PyInstaller includes the interpreter and Tk;
users do not install Python. Its spec explicitly collects Streamlit resources,
application metadata, the dashboard script, dynamically imported parsers, and
third-party license texts. The console-free executable dispatches its own child
server mode; it never invokes an external Python executable when frozen.

One-file offers no functional advantage for this beta, adds extraction/startup
work and makes diagnostics harder. Nuitka would add compiler/toolchain complexity
without an identified performance or compatibility requirement. A native webview
would add another runtime and lifecycle layer. No concrete Streamlit blocker has
been found; retain it. See the [PyInstaller spec documentation](https://pyinstaller.org/en/stable/spec-files.html).

## Implemented increments

1. Independent desktop storage and launcher. `%LOCALAPPDATA%\WerkelijkRendement`
   holds `config.toml`, `wr.sqlite`, `preferences.json`, server logs rotated at startup, and
   ephemeral instance metadata. CLI defaults remain unchanged. Updating/extracting
   another ZIP retains this directory; removing the ZIP does not delete it.
2. Loopback-only supervisor control API and Streamlit server on dynamically
   selected ports. An OS-held file lock prevents competing desktop instances.
   A second launch authenticates to the supervisor and opens the existing URL.
   Startup failures retry with another port (up to three attempts); readiness and
   a timeout govern browser launch. A random per-launch Streamlit URL prefix also
   prevents accepting another service's health response after a port race.
3. A visible native control window opens the browser, opens local storage, and
   shuts down the managed server. Closing the browser alone leaves this window
   running. Normal shutdown waits for the child and escalates if needed. A child
   watches its supervisor's process lifetime so forced supervisor termination
   does not leave a server running.
4. The native folder dialog executes on the supervisor's Tk main thread, requested
   by the dashboard through authenticated local IPC. Selection cancellation does
   nothing. Only a confirmed directory becomes an import source. Preferences are
   saved atomically; source documents are never modified. The importer scans
   recursively and now accepts uppercase `.PDF` as well as `.pdf`.
5. Dashboard import runs in a worker with progress, per-document outcomes, and
   cancellation between documents. Imported evidence remains available; cancelled
   runs still rebuild calculations and coverage. Existing evidence is recomputed
   before server startup to recover derived results after interrupted imports.
   A process-wide lock prevents
   overlapping imports across browser sessions. Cancellation does not interrupt
   extraction of the current PDF. Parser and calculation code remain UI independent.
6. Frozen builds use bundled `pypdf`, regardless of executables on PATH. Developer
   CLI runs retain optional Poppler and automatic pypdf fallback; Poppler invocation
   now has a timeout and suppresses a console on Windows. No Poppler binaries are
   redistributed, avoiding their additional license and packaging obligations.
7. Hash-locked release dependencies, Windows Actions build, versioned ZIP, SHA-256,
   release-note artifact, and a verifier for the actual executable. Ordinary
   development dependencies do not include PyInstaller.

## Privacy and local security

No telemetry is requested. Streamlit usage statistics are explicitly disabled;
CORS and XSRF remain enabled, file watching and static-directory serving are off.
See [Streamlit configuration](https://docs.streamlit.io/develop/api-reference/configuration/config.toml).
The desktop control API rejects browser Origin headers and requires a random token
in a header. It binds only to `127.0.0.1`; no CORS permission is issued. Local HTTP
calls bypass proxy environment settings. A random URL prefix reduces unsolicited
browser access to the dashboard. These measures are not isolation from other
software running as the same Windows user: that software can read the user's data
and instance credentials. Files inherit Windows user-directory permissions and
are not encrypted by the application.

The UI has no arbitrary path-entry or deletion endpoint. The native picker is the
source-location authority. Imports are read-only on sources; storage and exports
contain identifying information. Symlinks and directory junctions should be
reviewed in clean-machine tests; the selected folder may intentionally contain
links to other files. Directory exclusions are not yet implemented.

A full dependency outbound-traffic audit has not been completed. No new hosted
services or document uploads have been introduced. Browser extensions and the
browser's own network activity are outside the application's control. Verify
runtime network behavior before claiming a completed security audit.

## Build and automated verification

Build on Windows; PyInstaller does not cross-compile a Windows executable on Linux.
From a checkout, with Python 3.13.5 x64 installed **on the build machine only**:

```powershell
python -m pip install --require-hashes -r packaging/requirements.lock
python -m pip install --no-deps --no-build-isolation -e .
python -m pytest -q
python -m PyInstaller --noconfirm --clean packaging/desktop.spec
python packaging/verify.py dist/WerkelijkRendement/WerkelijkRendement.exe
```

`.github/workflows/windows.yml` performs these steps for pull requests, manual
runs, and version tags. A tag must match the version in `pyproject.toml`. It uploads
artifacts for review; it does not publish a public release or change brouns.tech.
To regenerate the dependency lock intentionally, use
`uv pip compile --universal --generate-hashes packaging/requirements.in -o packaging/requirements.lock`.
Keep its runtime requirements aligned with `pyproject.toml`. Builds have pinned
inputs and dependency hashes; byte-for-byte reproducibility is not asserted.

The frozen verifier runs from an unrelated directory with Python and Poppler
removed from PATH. It validates all eight discovered institution plugins, native
PDF extraction/import, exact synthetic interest, recomputation, and audit export.
On Windows it also tests launcher readiness, second-instance reuse, normal shutdown,
storage retention, and termination of the server after a forced supervisor exit.
On Linux it checks the frozen server directly without requiring a graphical desktop.

## Release gates and remaining work

- Run Windows CI and manually test on clean Windows 10 and 11 x64 machines with
  no Python/Poppler, offline, including non-ASCII usernames and folder paths.
- Verify real browser rendering and native picker focus, cancellation, repeated
  scans, unsupported/encrypted/image-only PDFs, interrupted imports, and restarts.
- Expand synthetic PDF fixtures across all supported institution layouts. Existing
  parser tests predominantly use extracted text; eight synthetic PDFs check one
  representative layout per institution and compare parsed values with the original
  fixture text. They do not prove equivalence for every bank's PDF layout. Pypdf
  availability alone does not establish compatibility. Do not declare full
  standalone document parity until this gate passes.
- Inspect third-party license inventory in the Windows bundle; the spec collects
  notices, but a complete redistribution-license review remains a release gate.
- Confirm network behavior, local browser-origin protections, folder links, error
  dialogs, and process cleanup on Windows. Test crowded ports and slow startup.
- Partner configuration still uses the persistent TOML file; an accessible editor
  and fuller Dutch onboarding belong to Phase 2. No tax rules were changed.
- Provide a UI for export/reset of the entire workspace. For now users can locate
  storage from the native launcher, download audit exports, and delete local data
  after shutting down (see the user guide).
- Installer/signing follow ZIP validation. Consider a per-user Inno Setup install
  without administrator elevation. Compare signing providers' current costs only
  when choosing a provider; signing is not a guarantee against SmartScreen
  reputation warnings. Never instruct users to disable Windows security.

This is a testable beta implementation, not evidence that the Windows acceptance
criteria have passed. Public release and website distribution remain gated on the
Windows results and clean-machine checks above.

## Local validation record — 13 October 2026

On Linux with the project's PyCharm-configured CPython 3.13.5 environment:

- Baseline: 60 tests passed.
- Updated suite: 69 tests passed, including native-extractor round trips for all
  eight institutions, storage and lock behavior, browser-origin rejection,
  cancellation, effective Streamlit security configuration, and dashboard
  onboarding/import through Streamlit's application test harness.
- PyInstaller one-folder build completed; the frozen verifier passed with an
  unrelated working directory and no Python or Poppler on PATH, including local
  server readiness and synthetic audit export.
- Standard source-distribution and wheel builds also completed successfully.
- The first frozen run exposed a bootstrap configuration issue; explicitly loading
  options before starting Streamlit corrected it. A regression test asserts the
  effective bind address and security options before server startup.
- Windows native UI/lifecycle verification has been authored for CI but has not
  run in this Linux environment. A Linux binary is not a Windows release artifact.

## Dutch/English localization increment

Application-owned launcher and dashboard messages use a shared Python catalog
in `wr.i18n`; PyInstaller collects it as an application module. No translation
files, additional runtime dependencies, or calculation-engine changes are needed.
`Language / Taal` offers `Nederlands` and `English`. Dutch is the initial desktop
language; the developer CLI dashboard defaults to English. The selected language
is stored atomically in a separate `language.json` beside the configuration,
preserving the existing folder preferences and financial database.

The launcher polls this shared preference to update its labels. Dashboard changes
apply on rerun; changing language in the launcher requires a dashboard reload.
Each browser session formats amounts independently, without a process-wide locale
change. Import jobs retain their progress and cancellation state during switching.
Known decision, coverage, document-type, and calculation-method labels are
translated at display time; unknown codes remain visible as recorded. The label
for complete coverage explicitly refers to available statements.

Evidence identifiers, names, account labels, raw source/parser errors, and audit
exports are not translated. System-owned Windows dialogs and Streamlit built-in
controls may retain their own language settings. Documentation remains English.
Automated tests exercise both languages, persisted settings, native label updates
with a test window, import cancellation after switching, and an unchanged financial
database. Native Windows rendering still requires the Windows verification gate.

Localization validation on Linux: 76 tests passed, including unchanged audit CSV
content after language switching. The one-folder build and frozen executable
verification also passed, with both translations, preference persistence, and
localized amount formatting exercised without Python or Poppler on PATH.

## Windows second-instance lock correction

The Windows artifact verifier exposed a cross-process lock failure: the second
launcher read byte zero of `instance.lock` before attempting the lock. Windows
mandatory byte-range locking denies that read while the first launcher owns the
byte, so a `PermissionError` opened an error dialog and the reuse check timed out.
The launcher now checks file size with `fstat` and catches contention during lock
initialization/acquisition. A separate-process regression checks contention and
recovery after release; same-process tests did not reveal this Windows behavior.

Frozen smoke failures now write a traceback rather than opening an unhandled-error
dialog. The verifier reports its phase and preserves allowlisted startup logs before
removing its synthetic workspace. Failed Windows runs upload these diagnostics and
include them in check annotations; instance credentials are excluded. The local
suite passes 84 tests. Windows artifact verification determines release readiness.
