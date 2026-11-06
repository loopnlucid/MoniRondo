from pathlib import Path
import tomllib

root = Path(SPECPATH).parent
version = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
a = Analysis(
    [str(root / 'packaging/entry.py')], pathex=[str(root / 'src')],
    binaries=[], datas=[(str(root / 'src/monirondo/resources'), 'monirondo/resources'),
                        (str(root / 'src/monirondo/locales'), 'monirondo/locales')],
    hiddenimports=['win32timezone'],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick',
              'PySide6.QtPdf', 'PySide6.QtPdfWidgets', 'tkinter', 'pytest', 'mypy'],
    noarchive=False,
)
# Keep only the desktop libraries/plugins used here. In particular qpdf must not
# silently pull a WebEngine/PDF runtime (and unrelated licensing) into the bundle.
qt_libraries = {'qt6core.dll', 'qt6gui.dll', 'qt6widgets.dll', 'qt6network.dll'}
plugins = {'qwindows.dll', 'qico.dll'}
def needed_binary(row):
    name = row[0].replace('\\', '/').lower()
    base = name.rsplit('/', 1)[-1]
    if '/plugins/' in name:
        return base in plugins
    if base.startswith('qt6') and base.endswith('.dll'):
        return base in qt_libraries
    return True
a.binaries = [row for row in a.binaries if needed_binary(row)]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='MoniRondo',
          debug=False, strip=False, upx=False, console=False,
          icon=str(root / 'assets/icon.ico'), manifest=str(root / 'packaging/app.manifest'),
          version=str(root / 'packaging/version_info.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=f'MoniRondo-{version}')
