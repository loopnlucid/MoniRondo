"""Acquire corresponding, unmodified Qt/PySide sources for redistribution."""
import hashlib
import json
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
destination = root / 'licenses/sources'
destination.mkdir(parents=True, exist_ok=True)
sources = {
    'qtbase-6.12.0.tar.gz': 'https://github.com/qt/qtbase/archive/refs/tags/v6.12.0.tar.gz',
    'pyside-setup-6.12.0.tar.gz': 'https://github.com/pyside/pyside-setup/archive/refs/tags/v6.12.0.tar.gz',
}
manifest = []
for name, url in sources.items():
    target = destination / name
    if not target.exists():
        temporary = target.with_suffix('.download')
        print(f'Downloading {name}', flush=True)
        with urllib.request.urlopen(url, timeout=90) as response, temporary.open('wb') as output:
            while block := response.read(1024 * 1024):
                output.write(block)
        temporary.replace(target)
    manifest.append({'file': name, 'url': url, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
(destination / 'sources.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print('Corresponding Qt/PySide sources ready')
