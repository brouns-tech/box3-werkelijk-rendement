# Build on the target OS. Writable financial data is never part of this bundle.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
streamlit_data, streamlit_binaries, streamlit_hidden = collect_all('streamlit')
data = streamlit_data + copy_metadata('box3-werkelijk-rendement', recursive=True)
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
    binaries=streamlit_binaries, datas=data,
    hiddenimports=streamlit_hidden + collect_submodules('wr') + collect_submodules('dashboard'),
    excludes=['pytest'], noarchive=False)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True,
    name='WerkelijkRendement', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False)
collection = COLLECT(exe, analysis.binaries, analysis.datas,
    strip=False, upx=False, name='WerkelijkRendement')
