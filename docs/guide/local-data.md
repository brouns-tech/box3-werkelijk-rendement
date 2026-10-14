# Manage local data

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
