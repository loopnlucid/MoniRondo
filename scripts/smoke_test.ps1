param([string]$Exe = '')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Exe) {
    # Default to the build that matches the version in pyproject.toml.
    $version = (Select-String -LiteralPath (Join-Path $projectRoot 'pyproject.toml') -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
    $Exe = Join-Path $projectRoot "dist\MoniRondo-$version\MoniRondo.exe"
}
$resolvedExe = (Resolve-Path -LiteralPath $Exe).Path
$smokeRoot = Join-Path $projectRoot 'artifacts\smoke-profile'
New-Item -ItemType Directory -Path $smokeRoot -Force | Out-Null
$previousAppData = $env:APPDATA
$previousLocalAppData = $env:LOCALAPPDATA
try {
    $env:APPDATA = $smokeRoot
    $env:LOCALAPPDATA = $smokeRoot
    $process = Start-Process -FilePath $resolvedExe -ArgumentList '--smoke-test' -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(30000)) { Stop-Process -Id $process.Id; throw 'Smoke test: startup or shutdown hangs.' }
    if ($process.ExitCode -ne 0) { throw "Smoke test failed: exit code $($process.ExitCode)" }
} finally {
    $env:APPDATA = $previousAppData
    $env:LOCALAPPDATA = $previousLocalAppData
}
Write-Output 'Smoke test passed (startup, native capture, hotkey message path, tray, shutdown).'
