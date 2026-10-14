import hashlib
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def release_tools():
    path = Path(__file__).resolve().parents[1] / 'packaging/prepare_release.py'
    spec = importlib.util.spec_from_file_location('release_tools', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('version,prerelease', [('0.1.0', 'true'), ('1.0.0', 'false'), ('2.1.0b1', 'true'), ('2.1.0rc1', 'true'), ('2.1.0.dev1', 'true')])
def test_release_versions_and_beta_promotion(release_tools, version, prerelease):
    assert release_tools.release_metadata(version, f'v{version}') == {
        'version': version, 'tag': f'v{version}', 'prerelease': prerelease,
    }


@pytest.mark.parametrize('version,tag', [('0.1.0', 'v0.2.0'), ('0.1.0', '0.1.0'), ('../0.1.0', None), ('0.1.0\nmalicious=true', None), ('0.01.0', None)])
def test_invalid_release_metadata_cannot_select_files_or_outputs(release_tools, version, tag):
    with pytest.raises(ValueError):
        release_tools.release_metadata(version, tag)


@pytest.fixture
def artifacts(tmp_path):
    directory = tmp_path / 'artifacts'
    directory.mkdir()
    names = ['WerkelijkRendement-0.1.0-windows-x64.zip', 'WerkelijkRendement-0.1.0-linux-x86_64.AppImage', 'WerkelijkRendement-0.1.0-linux-x86_64.tar.gz']
    for name in names:
        data = f'synthetic release payload: {name}'.encode()
        (directory / name).write_bytes(data)
        (directory / f'{name}.sha256').write_text(f'{hashlib.sha256(data).hexdigest()}  {name}\n')
    # Windows builds also include notes, but publication uses version-specific notes.
    (directory / 'RELEASE-NOTES.md').write_text('platform-only build notes')
    return directory, names


def test_release_contains_all_platform_downloads_checksums_and_curated_notes(release_tools, artifacts, tmp_path):
    directory, names = artifacts
    notes = tmp_path / '0.1.0.md'
    notes.write_text('# Desktop beta 0.1.0\n')
    output = tmp_path / 'release'
    files = release_tools.prepare_release('0.1.0', directory, notes, output)
    assert {file.name for file in files} == set(names) | {f'{name}.sha256' for name in names} | {'RELEASE-NOTES.md'}
    assert (output / 'RELEASE-NOTES.md').read_bytes() == notes.read_bytes()
    assert all((output / name).read_bytes() == (directory / name).read_bytes() for name in names)


@pytest.mark.parametrize('failure', ['missing', 'empty', 'corrupt', 'wrong-filename', 'missing-checksum', 'missing-notes'])
def test_incomplete_or_corrupt_payload_blocks_publication(release_tools, artifacts, tmp_path, failure):
    directory, names = artifacts
    asset = directory / names[1]
    checksum = directory / f'{names[1]}.sha256'
    notes = tmp_path / '0.1.0.md'
    notes.write_text('Desktop beta\n')
    if failure == 'missing':
        asset.unlink()
    elif failure == 'empty':
        asset.write_bytes(b'')
    elif failure == 'corrupt':
        asset.write_bytes(b'changed payload')
    elif failure == 'wrong-filename':
        checksum.write_text('0' * 64 + '  ../other.AppImage\n')
    elif failure == 'missing-checksum':
        checksum.unlink()
    else:
        notes.unlink()
    output = tmp_path / 'release'
    with pytest.raises(ValueError):
        release_tools.prepare_release('0.1.0', directory, notes, output)
    assert not output.exists()


def test_release_output_cannot_mix_in_unvalidated_files(release_tools, artifacts, tmp_path):
    directory, _ = artifacts
    notes = tmp_path / '0.1.0.md'
    notes.write_text('Desktop beta\n')
    output = tmp_path / 'release'
    output.mkdir()
    unrelated = output / 'unvalidated.txt'
    unrelated.write_text('preserve this file')
    with pytest.raises(ValueError, match='fresh directory'):
        release_tools.prepare_release('0.1.0', directory, notes, output)
    assert list(output.iterdir()) == [unrelated]
