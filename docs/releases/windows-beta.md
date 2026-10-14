# Windows beta 0.1.0 — release candidate

- One-folder, console-free launcher for the existing local Streamlit dashboard.
- Native document-folder selection, import progress, cancellation, and outcomes.
- Direct browser startup with a hidden supervisor and on-demand native dialogs.
- Dutch/English dashboard and dialogs, saved language preference, and localized amounts.
- Persistent per-user database and configuration; existing CLI preserved.
- Bundled Python PDF extraction, eight existing institution plugins, audit export.
- Loopback-only services, telemetry disabled, authenticated launcher controls.
- Versioned archive, locked dependencies, checksum, and frozen smoke verification.

Windows 10/11 x64 are intended targets. This candidate is unsigned. Do not disable
Windows protection. Windows CI, clean-machine usability, full PDF-layout parity,
and license/network review are release gates; consult [Windows builds](../development/windows-builds.md).
No calculation rules or institution coverage have changed. No public release or
website update is performed by the build workflow.
