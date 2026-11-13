# Builds the Deskvert release: dist\Deskvert (app folder), release\Deskvert-Setup-<ver>.exe and
# release\Deskvert-<ver>-portable.zip.
# Usage (from the project folder):  powershell -ExecutionPolicy Bypass -File tools\build_release.ps1
#
# -Stage app      only the app folder (dist\Deskvert)
# -Stage package  only the portable zip and the installer, from an existing dist\Deskvert
# -Stage all      both (the default)
# The release workflow builds in two stages so Deskvert.exe can be code-signed in between: the installer
# and the zip then carry the signed app.

param([ValidateSet("all", "app", "package")] [string]$Stage = "all")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
$version = (Select-String -Path "app\__init__.py" -Pattern '__version__ = "([^"]+)"').Matches[0].Groups[1].Value
Write-Host "Building Deskvert $version ($Stage)" -ForegroundColor Cyan

if ($Stage -in @("all", "app")) {
    & $py -m pip install --quiet pyinstaller
    & $py tools\make_icon.py

    Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
    & $py -m PyInstaller deskvert.spec --noconfirm --clean
    if (-not (Test-Path "dist\Deskvert\Deskvert.exe")) { throw "PyInstaller build failed" }
}

if ($Stage -in @("all", "package")) {
    if (-not (Test-Path "dist\Deskvert\Deskvert.exe")) { throw "No app to package: run with -Stage app first" }
    New-Item -ItemType Directory -Force release | Out-Null
    $zip = "release\Deskvert-$version-portable.zip"
    Remove-Item $zip -ErrorAction SilentlyContinue
    Compress-Archive -Path "dist\Deskvert\*" -DestinationPath $zip

    $iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
              "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($iscc) {
        & $iscc "/DAppVersion=$version" "installer\deskvert.iss"
    } else {
        Write-Warning "Inno Setup not found: skipped the installer (portable zip is ready). Install it with: winget install JRSoftware.InnoSetup"
    }
    Get-ChildItem release | Select-Object Name, @{n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } }
}
