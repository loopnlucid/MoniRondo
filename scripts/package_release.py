"""Bundle the built app, matching source, documentation and dependency notices."""
import hashlib
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

root = Path(__file__).resolve().parents[1]
version = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
release = root / f'dist/MoniRondo-{version}'
assert (release / 'MoniRondo.exe').is_file(), 'Build the Windows executable first'
subprocess.run([sys.executable, str(root / 'scripts/package_source.py')], check=True)
for name in ['README.md', 'LICENSE', 'CHANGELOG.md']:
    shutil.copy2(root / name, release / name)
shutil.copytree(root / 'docs', release / 'docs', dirs_exist_ok=True)
subprocess.run([sys.executable, str(root / 'scripts/collect_licenses.py'), str(release / 'LICENSES')], check=True)
shutil.copy2(root / f'dist/MoniRondo-{version}-source.zip', release / 'MoniRondo-source.zip')
output = root / f'dist/MoniRondo-{version}-win64.zip'
with ZipFile(output, 'w', compression=ZIP_DEFLATED, compresslevel=6) as archive:
    for path in sorted(release.rglob('*')):
        if path.is_file():
            # Already compressed corresponding-source archives need no second compression pass.
            kind = ZIP_STORED if path.suffix in ('.gz', '.xz', '.zip') else ZIP_DEFLATED
            archive.write(path, path.relative_to(release).as_posix(), compress_type=kind)
digest = hashlib.sha256(output.read_bytes()).hexdigest()
output.with_suffix('.zip.sha256').write_text(f'{digest}  {output.name}\n', encoding='ascii')
print(f'Release: {output}\nSHA256: {digest}')
