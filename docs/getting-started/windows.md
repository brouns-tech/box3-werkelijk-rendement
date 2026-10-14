# Werkelijk Rendement — Windows beta

This beta reconstructs Box 3 returns from supported financial documents.
Processing takes place locally. The application is free and open-source.

Use **Language / Taal** in the dashboard to choose **Nederlands** or
**English**. The desktop starts in Dutch unless a language preference has been
saved. The CLI-launched dashboard defaults to English. This guide uses English
labels and includes Dutch equivalents where helpful.

1. Extract the entire ZIP into a folder of your choice.
2. Open `WerkelijkRendement.exe`. Keep its accompanying `_internal` folder.
3. The application opens the dashboard in your default browser, with no launcher window.
4. Open **Documents** (`Documenten`), choose **Select folder** (`Map selecteren`), then **Scan documents and calculate**
   (`Documenten scannen en berekenen`).
5. Review import messages, document coverage, calculations, and the audit export.
6. Use **Exit application** (`Applicatie afsluiten`) in the dashboard sidebar to stop the application.
   Closing the browser tab alone does not stop the application.

You do not need to install Python or Poppler. The intended platforms are Windows
10 and 11, 64-bit. The availability of a ZIP does not prove that all compatibility
checks have been completed; consult the release information.

After an extraction update, scan the saved document folder again. The app
reprocesses older imports, preserves your taxpayer settings, and refreshes the
dashboard automatically. A warning replaces the comparison until older parsed
documents have been refreshed.

Opening the application again reuses the existing dashboard. If a problem occurs,
the launcher tells you where to find the log file. You can cancel folder selection.
During import, you can stop after the current document; documents already imported
remain stored. Source PDFs are not modified.

## Local data

Data is stored in `%LOCALAPPDATA%\WerkelijkRendement`. Use **Open local data**
(`Lokale gegevens openen`) in the dashboard sidebar to locate this folder. The database,
configuration, folder preference, and logs are retained across updates and after
removing the extracted application. They can contain personal and financial
information. The application does not encrypt the database. Your language
preference is saved separately in `language.json` in this folder.

Changing language in the dashboard updates its controls, tables, and amount
formatting immediately. Native dialogs follow the saved preference automatically.
Changing language does not change stored financial facts or calculations.
Source document text, technical parser errors, and audit exports retain their
original content. Windows system dialogs and Streamlit's built-in controls may
use their own language settings.

To make a backup, close the application and copy this data folder. For a complete
reset, delete the contents of the folder after closing the application. The next
launch creates a new empty workspace. Your original PDFs remain untouched.
Downloaded audit exports are stored separately; delete them separately if you
want to remove all derived financial data.

Review taxpayer names, aliases, and minor-child profiles in **Taxpayers**.
Manage the database and institution options in **Settings**. Workspace settings
and the selected folder are stored in `.wr-settings.json`; beta `config.toml`
and `preferences.json` values migrate once. The retired files are ignored afterward.
**Settings → Reset workspace** removes imported data and profiles while retaining
the database location, original PDFs, and separately downloaded audit exports.

## Limitations

Only supported document layouts are processed. Unknown documents are shown as
unrecognized. Scans without a text layer are not automatically read. Importing
all selected documents does not prove that all your assets, debts, or partner
documents are represented. Missing evidence can produce an indeterminate result.
Verify calculations and underlying documents before making a tax decision. The
application is not a tax-return submission channel and is not affiliated with the
Belastingdienst (Dutch tax authority).

An unsigned beta may trigger a Windows security warning. Verify the download's
origin and SHA-256 checksum; do not disable security protections. If in doubt,
use the source project or wait for a verified release.
