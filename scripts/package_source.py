"""Create a self-contained source ZIP that includes a readable project inventory."""
import tomllib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parents[1]
version = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
folders = ['src', 'tests', 'scripts', 'assets', 'packaging', 'docs', '.github', 'licenses']
root_files = ['README.md', 'LICENSE', 'CHANGELOG.md', 'CONTRIBUTING.md', 'CODE_OF_CONDUCT.md', 'SECURITY.md',
              'pyproject.toml', 'requirements-lock.txt', '.gitignore', '.gitattributes', '.editorconfig']
files = [root / n for n in root_files if (root / n).is_file()]
for name in folders:
    files.extend(p for p in (root / name).rglob('*') if p.is_file()
                 and '__pycache__' not in p.parts and 'sources' not in p.relative_to(root / name).parts
                 and not any(part.endswith('.egg-info') for part in p.parts))
files = sorted(set(files))
names = [p.relative_to(root).as_posix() for p in files]
tree = ('MoniRondo project files (generated build/cache and third-party archives omitted)\n\n'
        + '\n'.join(sorted([*names, 'PROJECT-TREE.txt'], key=str.casefold)) + '\n')
output = root / f'dist/MoniRondo-{version}-source.zip'
output.parent.mkdir(exist_ok=True)
with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
    for path, name in zip(files, names, strict=True):
        archive.write(path, 'MoniRondo/' + name)
    archive.writestr('MoniRondo/PROJECT-TREE.txt', tree)
print(output)
