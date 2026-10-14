# Werkelijk Rendement — Linux beta

The Linux beta uses the same local document importer, calculation engine,
Dutch/English interface, and audit exports as the Windows application.
Python and Poppler are bundled or unnecessary; no separate installation of either
is required.

## Download formats

**AppImage** is the main single-file download. Make it executable using your file
manager's permissions dialog, then open it. You can also run:

```sh
chmod +x WerkelijkRendement-0.1.0-linux-x86_64.AppImage
./WerkelijkRendement-0.1.0-linux-x86_64.AppImage
```

If FUSE mounting is unavailable, use the runtime's extraction mode instead:

```sh
./WerkelijkRendement-0.1.0-linux-x86_64.AppImage --appimage-extract-and-run
```

This temporarily extracts application files, not your financial data. Alternatively,
use the **portable `.tar.gz` archive**: extract the complete archive and open
`AppRun` inside its `WerkelijkRendement` folder. Keep the `usr` directory beside it.
Neither format requires administrator access or registers an automatic updater.
Verify the downloaded artifact against its accompanying SHA-256 checksum.

## Compatibility

The release build targets Linux x86-64 with glibc 2.35 or newer, using Ubuntu 22.04
as its build baseline. A graphical desktop, X11 or XWayland, a default browser,
and `xdg-open` from the desktop's `xdg-utils` package are required. Tk's folder
picker uses the X11 interface; native Wayland-only operation has not been validated.
Other architectures and musl-based systems such as Alpine are not release targets.

Build artifacts must pass CI and clean-desktop verification before a public
compatibility claim is made. A local build made on a newer distribution can require
a newer glibc than the release baseline. See [Linux packaging](linux-packaging.md)
for the validation record and release gates.

## Using the application

The launcher opens the dashboard in your default browser. Use **Language / Taal**
to select **Nederlands** or **English**. Open **Documents**, choose **Select folder**, then **Scan
documents and calculate**. Review unsupported files, document coverage, and the
underlying source evidence before relying on a result. You can cancel importing
after the current document. Original documents are never modified.

A second launch opens the existing dashboard. Use **Exit** in the launcher to
stop the local server. Closing the browser tab alone leaves the launcher running.
**Open local data** opens your file manager. No application service is installed.

Data is stored in `$XDG_DATA_HOME/WerkelijkRendement`, normally
`~/.local/share/WerkelijkRendement`. The database, configuration, selected folder,
language preference, and logs remain there after updating or deleting the application.
Close the application before backing up or deleting that directory. Deleting it
resets the workspace without deleting original PDFs. Audit downloads are stored
separately and must be deleted separately if you want to remove all derived data.
The application does not encrypt its database.

Use **Taxpayers** to review names, aliases, and minor-child profiles, and
**Settings** for storage, institution options, and resetting imported data.
The selected folder and workspace settings live in `.wr-settings.json`.
Earlier beta TOML settings and folder preferences migrate once; they are ignored
after migration, including after a workspace reset.

Both formats run as your desktop user and are not sandboxes. The services bind to
loopback, source processing stays local, and usage telemetry is disabled. Only
supported document layouts are imported; importing every selected file does not
establish completeness of your total financial situation. The application is not
a tax-return submission channel and is not affiliated with the Belastingdienst.
