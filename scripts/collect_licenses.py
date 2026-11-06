"""Copy installed distribution license texts and Qt LGPL notices into the release."""
import hashlib
import importlib.metadata as md
import json
import shutil
import sys
from pathlib import Path

target = Path(sys.argv[1])
target.mkdir(parents=True, exist_ok=True)
packages = ['PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6', 'pywin32',
            'pyinstaller', 'pyinstaller-hooks-contrib', 'pywin32-ctypes']
for name in packages:
    dist = md.distribution(name)
    folder = target / name
    folder.mkdir(exist_ok=True)
    for entry in dist.files or []:
        if ('license' in str(entry).lower() or 'copying' in str(entry).lower()) and dist.locate_file(entry).is_file():
            source = Path(dist.locate_file(entry))
            relative = Path(*(p for p in entry.parts if p not in ('..', '.')))
            destination = folder / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    (folder / 'PACKAGE.txt').write_text(f'{dist.metadata["Name"]} {dist.version}\n{dist.metadata.get("License-Expression", dist.metadata.get("License", "See license texts"))}\n', encoding='utf-8')
python_license = Path(sys.base_prefix) / 'LICENSE.txt'
if python_license.exists():
    shutil.copy2(python_license, target / 'Python-LICENSE.txt')
extra = Path(__file__).resolve().parents[1] / 'licenses'
source_dir = extra / 'sources'
for item in json.loads((source_dir / 'sources.json').read_text(encoding='utf-8')):
    assert hashlib.sha256((source_dir / item['file']).read_bytes()).hexdigest() == item['sha256'], 'Third-party source archive checksum mismatch'
if extra.exists():
    shutil.copytree(extra, target / 'Qt-open-source', dirs_exist_ok=True)
