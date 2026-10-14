# Werkelijk Rendement

_Reconstruct Dutch Box 3 actual returns from your own financial documents._

Werkelijk Rendement reads supported bank, broker, and income-tax PDFs, compares
actual return (`werkelijk rendement`) with the filed fictitious return
(`forfaitair rendement`), and exports the evidence behind the calculation.
Free, open-source, and processed entirely on your computer, with a Dutch/English
interface and fiscal-partner support.

![Dashboard with synthetic example data](docs/assets/dashboard-overview.png)

## Download and launch

Use the desktop binaries from [GitHub Releases](https://github.com/brouns-tech/box3-werkelijk-rendement/releases).
No Python installation or separate PDF tools are needed.

- **Windows:** extract the entire ZIP and open `WerkelijkRendement.exe`.
- **Linux:** make the AppImage executable and open it, or extract the portable
  `.tar.gz` and open `AppRun`.

The dashboard opens in your browser. Check the release notes and SHA-256 checksum
for your download. **No public release has been published yet**; this is the
intended download route once binaries are released.
See the [Windows](docs/windows-beta.md) and [Linux](docs/linux-beta.md) guides
for platform requirements and troubleshooting.

## Import, review, compare

1. **Documents:** choose **Select folder**, then **Scan documents and calculate**.
   PDFs in subfolders are included; filenames do not matter. Review recognized,
   unsupported, and failed imports. Your original documents are never modified.
2. **Taxpayers:** review detected names and their assignments, aliases, and any
   suggested minor children. Correct mistaken matches and leave uncertain names
   unassigned. Two taxpayer profiles do not establish fiscal partnership.
3. **Overview:** select a tax year, check coverage and warnings, then review the
   actual-return comparison and account breakdown against your documents.
   **Download audit export** saves the calculation and source evidence as a ZIP.

Use **Language / Taal** to switch between Dutch and English. Your selected folder,
settings, and imported data are remembered. Use **Exit application** in the sidebar
to stop the app; closing the browser tab leaves it running.

See the [user guide](docs/user-guide.md) for detailed instructions.

## Coverage and privacy

Supported layouts include **ING, Rabobank, SNS, Raisin, Revolut, DEGIRO, flatex,
and Belastingdienst** documents. Check the [compatibility matrix](docs/supported-documents.md)
for exact layouts and limitations. Tax comparison policies cover **2017–2025**.

Importing all selected files does not prove your financial situation is complete.
Missing or unsupported evidence can leave the result indeterminate. Verify the
calculation before making a tax decision; this is an analysis aid, not a filing
service or tax advice, and is not affiliated with the Belastingdienst.

Financial data stays local, without accounts or usage telemetry. The database
and audit exports contain sensitive information and are not encrypted by the app.

## Develop and contribute

See [Contributing](CONTRIBUTING.md) for source installation, tests, and parser
contributions, and the [CLI guide](docs/cli.md) for developer commands and synthetic
demo data. Never submit real financial documents or personal data.
