# Build on the target OS. Writable financial data is never part of this bundle.
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

if sys.platform.startswith('linux'):
    import _tkinter
    if not getattr(_tkinter, '__file__', None):
        raise RuntimeError('Linux desktop builds require CPython with dynamically linked Tcl/Tk. '
                           'This interpreter has built-in static Tk/X11, which can crash on labels. '
                           'Use the Ubuntu release workflow or a compatible CPython build.')

root = Path(SPECPATH).parent
streamlit_data, streamlit_binaries, streamlit_hidden = collect_all('streamlit')
explorer_data, explorer_binaries, explorer_hidden = collect_all('streamlit_explorer')
pdfium_data, pdfium_binaries, pdfium_hidden = collect_all('pypdfium2')
raw_data, raw_binaries, raw_hidden = collect_all('pypdfium2_raw')
data = streamlit_data + copy_metadata('box3-werkelijk-rendement', recursive=True)
data += explorer_data
data += pdfium_data + raw_data
data += [(str(root / 'dashboard' / 'app.py'), 'dashboard'), (str(root / 'LICENSE'), 'licenses/project')]
# Retain third-party license texts in the release, even if upstream metadata lacks them.
import importlib.metadata
for distribution in importlib.metadata.distributions():
    for item in distribution.files or []:
        if 'license' in str(item).lower() or 'copying' in str(item).lower():
            source = distribution.locate_file(item)
            if source.is_file():
                data.append((str(source), 'licenses/' + distribution.metadata['Name'] + '/' + str(Path(item).parent)))

analysis = Analysis([str(root / 'packaging' / 'entrypoint.py')],
    pathex=[str(root / 'src'), str(root)],
    binaries=streamlit_binaries + explorer_binaries + pdfium_binaries + raw_binaries, datas=data,
    hiddenimports=streamlit_hidden + explorer_hidden + pdfium_hidden + raw_hidden + collect_submodules('wr') + collect_submodules('dashboard'),
    excludes=['pytest'], noarchive=False)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True,
    name='WerkelijkRendement', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False)
collection = COLLECT(exe, analysis.binaries, analysis.datas,
    strip=False, upx=False, name='WerkelijkRendement')
