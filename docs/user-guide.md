# User guide

This guide uses the English interface labels. Choose **Language / Taal** to
switch between English and Dutch; the preference is saved. Source names, document
text, and audit evidence retain their original content.

## Launch the application

Download a desktop binary from [GitHub Releases](https://github.com/brouns-tech/box3-werkelijk-rendement/releases)
when available. Follow the [Windows](windows-beta.md) or [Linux](linux-beta.md)
guide to extract or launch it. You do not need Python or a separate PDF extractor.

The dashboard opens in your default browser and runs locally. Opening the
application again reuses the running instance. Closing the browser tab leaves
the application running; **Exit application** in the sidebar stops it.

## Import documents

1. Collect your annual bank statements, investment statements, and income-tax
   returns in a folder. Subfolders are included, and filenames need no special format.
   Check the [supported-document matrix](supported-documents.md) for recognized layouts.
2. Open **Documents** and choose **Select folder** to use the native folder picker.
   The selected location is remembered, so you can reuse it on later launches.
3. Choose **Scan documents and calculate**. Watch the progress and review the
   import report. You can stop after the current document; completed imports are retained.
4. Review unsupported or failed documents before relying on the calculation.
   A recognized institution does not mean every statement layout is supported.

Imports read PDFs directly from the selected folder on your computer. They do
not upload or modify your documents. Identical document contents are deduplicated,
so adding files and scanning the folder again does not count them twice.

A skipped or failed document may contain information needed for your calculation.
Check its explanation and compare it with the compatibility matrix. Image-only
scans are not automatically read; obtain the original text-based PDF if available.
A successful import is evidence of processing, not proof that all accounts or
assets are represented.

## Review taxpayers and ownership

Open **Taxpayers** after importing, and again after adding new documents.
Tax returns identify filers and fiscal partners. Other distinct account holders
may be suggested as minor children; these suggestions require your review.

- Check each **Canonical name**, then review **Names found in documents**.
  Assign each source name to the correct person, or leave it **Unassigned** if uncertain.
  Assignments save and update the analysis immediately, including pending name or alias edits.
- Use **Aliases (one per line)** for additional spellings belonging to the same
  person. A shared surname or ambiguous initials alone do not establish identity.
  Source names remain preserved in the evidence.
- Name and alias edits show a green **✓** to save all pending profile edits and
  update the analysis, and a red **✕** to discard them.
- Check **Minor children (assets attributed to parents)** carefully. A missing
  adult tax return does not prove someone is a child. Review age and parental
  authority for each tax year; changes in age or custody are not automatically modeled.
  **Add child** creates a profile; **Delete child** removes the profile and unassigns
  its source names without deleting documents.

Two primary taxpayer profiles do not imply full-year fiscal partnership.
Partnership and allocation come from the relevant tax return. For full-year
fiscal partners, the comparison uses the combined return and filed taxable-base
allocation. Missing partner documents can prevent a definitive combined result.

Child accounts appear as joint (purple) in the overview. For individual returns,
child assets are attributed entirely to a sole configured parent, or equally to
two configured parents. Children do not receive separate tax-decision rows.
Review whether this matches your circumstances before using the result.

## Understand the overview

Select **Tax year** in **Overview**, then work through these sections:

1. **Coverage** and warnings: establish which evidence is present and which
   accounts or figures are missing or partial. An actual-return amount can be a
   known subtotal while the overall result remains indeterminate.
2. **Decision overview**: inspect the actual-return and fictitious-return
   comparison, taxpayer allocation, and result status. A missing-data or
   manual-review status is not a definitive recommendation.
3. **Account overview**: check account holders, individual/joint allocation,
   Box 3 inclusion, opening and closing values, interest, dividends, and
   calculated return against the original statements.
4. **Import diagnostics**: review counts of parsed, skipped, and failed documents
   by institution and document type. Return to **Documents** for document details.

Policies are implemented for 2017–2025. Later years require manual review rather
than a guessed future policy. Unsupported assets or incomplete partner coverage
may also prevent a meaningful tax comparison. Importing every PDF in your folder
cannot establish completeness of your entire financial situation.

Choose **Download audit export** to save a ZIP for the selected year. It includes
yearly totals, asset calculations, source facts, and tax results. Use it alongside
the original PDFs to inspect the inputs and calculation assumptions.

## Manage local data

The application remembers imported data and settings across restarts and updates.
Use **Open local data** in the sidebar to locate the storage directory:

- Windows: `%LOCALAPPDATA%\WerkelijkRendement`.
- Linux: `$XDG_DATA_HOME/WerkelijkRendement`, normally `~/.local/share/WerkelijkRendement`.

The database, saved folder, profiles, aliases, and logs can contain personal and
financial information. The app does not encrypt them. Audit exports are stored
separately wherever your browser saves downloads; review them before sharing.
Close the application before copying the data directory for a backup.

Use **Settings** to change the database location or institution-specific options.
Choosing another database changes the dataset you are viewing.
**Settings → Reset workspace** requires confirmation and removes imported records,
extracted facts, calculation results, taxpayer profiles, aliases, institution
options, and the saved document folder. It retains the database location and
leaves original PDFs and downloaded audit exports untouched.

To remove the stored application data completely, exit the application and delete
its data directory. Separately delete downloaded exports if needed. Removing the
application binary alone does not remove your workspace.
