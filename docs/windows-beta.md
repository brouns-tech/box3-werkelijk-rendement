# Werkelijk Rendement — Windows beta

This beta reconstructs Box 3 returns from supported financial documents.
Processing takes place locally. The application is free and open-source.

The current desktop controls use Dutch labels, quoted below to help you locate
them. Documentation is maintained in English; the application may offer Dutch
and English interfaces.

1. Extract the entire ZIP into a folder of your choice.
2. Open `WerkelijkRendement.exe`. Keep its accompanying `_internal` folder.
3. The launcher opens the dashboard in your default browser.
4. Choose **Select folder** (`Map selecteren`), then **Scan documents and calculate**
   (`Documenten scannen en berekenen`).
5. Review import messages, document coverage, calculations, and the audit export.
6. Close the application using **Exit** (`Afsluiten`) in the launcher window.
   Closing the browser tab alone does not stop the application.

You do not need to install Python or Poppler. The intended platforms are Windows
10 and 11, 64-bit. The availability of a ZIP does not prove that all compatibility
checks have been completed; consult the release information.

Opening the application again reuses the existing dashboard. If a problem occurs,
the launcher tells you where to find the log file. You can cancel folder selection.
During import, you can stop after the current document; documents already imported
remain stored. Source PDFs are not modified.

## Local data

Data is stored in `%LOCALAPPDATA%\WerkelijkRendement`. Use **Open local data**
(`Lokale gegevens openen`) in the launcher to locate this folder. The database,
configuration, folder preference, and logs are retained across updates and after
removing the extracted application. They can contain personal and financial
information. The application does not encrypt the database.

To make a backup, close the application and copy this data folder. For a complete
reset, delete the contents of the folder after closing the application. The next
launch creates a new empty workspace. Your original PDFs remain untouched.
Downloaded audit exports are stored separately; delete them separately if you
want to remove all derived financial data.

Optional fiscal-partner names, aliases, and institution-specific settings can be
configured in `config.toml` in this data folder. See the repository documentation.

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
