# Builds the Tapshift release: dist\Tapshift (app folder), release\Tapshift-Setup-<ver>.exe and
# release\Tapshift-<ver>-portable.zip.
# Usage (from the project folder):  powershell -ExecutionPolicy Bypass -File tools\build_release.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
$version = (Select-String -Path "app\__init__.py" -Pattern '__version__ = "([^"]+)"').Matches[0].Groups[1].Value
Write-Host "Building Tapshift $version" -ForegroundColor Cyan

& $py -m pip install --quiet pyinstaller
& $py tools\make_icon.py

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
& $py -m PyInstaller tapshift.spec --noconfirm --clean
if (-not (Test-Path "dist\Tapshift\Tapshift.exe")) { throw "PyInstaller build failed" }

New-Item -ItemType Directory -Force release | Out-Null
$zip = "release\Tapshift-$version-portable.zip"
Remove-Item $zip -ErrorAction SilentlyContinue
Compress-Archive -Path "dist\Tapshift\*" -DestinationPath $zip

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    & $iscc "/DAppVersion=$version" "installer\tapshift.iss"
} else {
    Write-Warning "Inno Setup not found: skipped the installer (portable zip is ready). Install it with: winget install JRSoftware.InnoSetup"
}
Get-ChildItem release | Select-Object Name, @{n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } }
