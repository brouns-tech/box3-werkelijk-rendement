# Linux distribution assessment and implementation

## Format choice

| Format | Benefit for this project | Cost or limitation | Decision |
| --- | --- | --- | --- |
| AppImage | One downloadable executable; reuses the existing frozen bundle; no administrator install | FUSE or extraction mode; host glibc and graphical desktop compatibility still matter | Primary beta download |
| Portable `.tar.gz` | Small packaging layer, easy inspection, no FUSE | Users must extract the complete directory; no automatic menu integration | Publish alongside AppImage |
| Flatpak | Desktop integration and an explicit sandbox/permissions model | Tk's picker would need a portal integration; the local server and external browser also need permission/lifecycle design | Revisit after the portable beta |
| `.deb` / RPM | Familiar native package management and menu entries | Separate distro families, dependency metadata, installation/update policy and more testing | Defer until user demand justifies it |
| Snap | Managed distribution and confinement options | Additional packaging/runtime and confinement integration | No concrete advantage identified for the first beta |

AppImage is a packaging mechanism, not a sandbox. Its runtime normally mounts a
filesystem with FUSE; extraction mode is an official alternative. See the
[AppImage architecture](https://docs.appimage.org/reference/architecture.html) and
[FUSE troubleshooting guidance](https://docs.appimage.org/user-guide/troubleshooting/fuse.html).
Flatpak file selection can use portals to grant selected-file access; our current
Tk picker does not do this. See the [Flatpak portal documentation](https://github.com/flatpak/flatpak/wiki/Portals).

## Shared application and Linux adaptations

`packaging/desktop.spec` now serves both Windows and Linux. The Streamlit UI,
launcher, institution plugins, Python PDF extraction, SQLite data model and tax
engine are shared. Linux has no separate frontend or calculation implementation.
The native launcher already uses Tk and a POSIX instance lock. Linux data remains
in the existing XDG data directory. The local-data button now works through
`xdg-open`, which also opens dashboard URLs in the host browser.

Host desktop helpers receive a clean library environment. PyInstaller modifies
`LD_LIBRARY_PATH`; propagating its bundled libraries into system browsers/file
managers can break them. Only external helpers receive the restored original
path; the bundled server process retains its required environment. See
[PyInstaller subprocess guidance](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#launching-external-programs-from-the-frozen-application).

The AppDir contains a relocatable `AppRun`, desktop entry, SVG icon, the frozen
bundle, English user guide, dependency lock and license notices. Arguments are
passed through without shell evaluation. No financial data is included. The
AppImage and archive both retain per-user state independently of their location.

## Build inputs and workflow

Linux x86-64 builds use Ubuntu 22.04 and CPython 3.13.5. This is a glibc 2.35
baseline, not a promise of compatibility with every Linux distribution. PyInstaller
does not bundle glibc; build on the oldest supported host. See its
[Linux compatibility guidance](https://pyinstaller.org/en/stable/usage.html#gnu-linux).
The local development host uses glibc 2.39, so its artifacts do not establish the
2.35 compatibility floor. The Docker daemon was unavailable; baseline verification
belongs to the Ubuntu 22.04 CI runner and clean-machine checks.

```sh
python -m pip install --require-hashes -r packaging/requirements.lock
python -m pip install --no-deps --no-build-isolation -e .
python -m pytest -q
python -m PyInstaller --noconfirm --clean packaging/desktop.spec
python packaging/package_linux.py
```

Run the build on Linux. `packaging/package_linux.py` downloads AppImage tooling
only at build time. `packaging/linux/tools.lock.json` pins numeric upstream release
asset IDs and SHA-256 digests, plus the exact runtime source revision. Downloaded
code is checked before execution. The runtime is passed explicitly to appimagetool,
avoiding its default download of the latest runtime. Tool updates require an
intentional lock change. Build inputs are pinned; byte-for-byte reproducibility
is not claimed.

Use a CPython build with a dynamic `_tkinter` extension. The uv-managed SDK in this
workspace statically links Tk/X11 and crashes when creating a text label, even
without PyInstaller. This matches the [upstream interpreter issue](https://github.com/astral-sh/python-build-standalone/issues/503).
The shared spec and Linux packager reject that known unsuitable build input.
The CI workflow uses `actions/setup-python` and verifies a real Tk label under
Xvfb before freezing; it does not use uv to install the release interpreter.

If rerunning packaging, remove the previous generated `dist/WerkelijkRendement.AppDir`
first. Staging deliberately refuses to overwrite an existing directory.
`.github/workflows/linux.yml` builds and tests the executable, AppImage, and extracted
archive, then uploads versioned artifacts and SHA-256 checksums. It uses Xvfb for
native-launcher verification and extraction mode for AppImage verification without
FUSE. It runs the application with Python and Poppler absent from PATH and a stub
host opener to avoid opening browsers during automated tests. It checks readiness,
instance reuse, normal shutdown, state retention, and server termination after
forced supervisor exit. Runtime wrappers are distinguished from the supervisor
through the authenticated local status response.

## Licenses and release gates

The bundle retains project/dependency license notices. The AppImage runtime's
[license](https://github.com/AppImage/type2-runtime/blob/8f39b89e2ac31e1640b3d3f7e9a5108e6ce805fa/LICENSE)
also lists its statically linked components, including LGPL-licensed libfuse.
The pinned runtime source archive and source revision are included for inspection
and rebuilding; upstream build instructions describe its additional dependencies.
Check the complete static-component notices and source/relinking obligations before
public redistribution. Including one runtime license file is not a completed
third-party compliance audit. No Poppler binaries are included.

Before publishing a stable download:

- Pass the Ubuntu 22.04 build and GUI verifier; run on a clean Ubuntu desktop and a
  representative second distro, offline and without Python/Poppler.
- Test AppImage FUSE mount and extraction paths, GNOME/KDE browser and file-manager
  integration, XWayland, spaces/non-ASCII paths, native folder selection and cancellation.
- Check interrupted imports, startup failures, full launcher/server cleanup, and
  shared state across archive/AppImage updates. Forced runtime-wrapper termination
  also needs manual testing; automated checks target the actual supervisor.
- Validate dependency/runtime licenses, glibc/shared-library requirements and
  outbound network behavior. Expand PDF-layout extraction fixtures as documented
  for Windows; the existing eight synthetic PDFs are not exhaustive bank coverage.

The workflows prepare downloadable artifacts for review. They do not create a
public GitHub release or update brouns.tech automatically. Public download links
should point to verified, versioned release artifacts after these gates pass.

## Local validation record

On the development host, 81 automated tests pass. Tests cover restored host
library paths, safe opener arguments, missing desktop helpers, checked downloads,
and relocatable AppDir metadata in addition to the existing calculation/parser and
localization regressions. AppImage generation using the pinned runtime and zstd,
portable-archive creation, and SHA-256 generation completed successfully.

Native launcher verification failed on the uv-managed interpreter before any
browser launch. A minimal label reproduced the X11 failure; this is an actual
interpreter limitation, not a passed GUI check. The generated local artifacts are
not release candidates. The new guards prevent generating more artifacts from
that interpreter.

At commit `d9e60be`, the [Ubuntu 22.04 Linux workflow](https://github.com/brouns-tech/box3-werkelijk-rendement/actions/runs/38393348360)
passed the tests, native GUI preflight, frozen-launcher lifecycle verification,
AppImage/archive packaging, and both final-artifact GUI checks. The `Linux-beta`
artifact contains the versioned AppImage, portable archive, and checksums. These
are tested beta artifacts; manual clean-desktop/FUSE checks and the remaining
license/network review still precede stable public distribution.
