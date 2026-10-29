# Builds dist\Faraday\Faraday.exe (one-folder, no console) with PyInstaller.
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
# Then install it for your user with packaging\install.ps1.

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $Root
try {
    python packaging\make_icon.py
    if ($LASTEXITCODE -ne 0) { throw "Icon generation failed" }
    python -m PyInstaller packaging\faraday.spec --noconfirm --clean --distpath dist --workpath build
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
    Write-Host "Built: $Root\dist\Faraday\Faraday.exe"
} finally {
    Pop-Location
}
