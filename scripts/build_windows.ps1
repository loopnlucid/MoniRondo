param([switch]$SkipChecks)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Create the Python venv and install requirements-lock.txt first; see README.' }
function Run-Python { & $pythonExe @args; if ($LASTEXITCODE -ne 0) { throw "Python command failed: $args" } }
if (-not $SkipChecks) {
    Run-Python -m pytest -q
    Run-Python -m ruff check .
    Run-Python -m mypy
}
Run-Python scripts/create_icon.py
if (-not (Test-Path -LiteralPath 'licenses\sources\sources.json')) {
    throw 'LGPL source archives are missing. Run .venv\Scripts\python.exe scripts/prepare_third_party.py first.'
}
Run-Python -m PyInstaller --noconfirm packaging/monirondo.spec
Run-Python scripts/package_release.py
