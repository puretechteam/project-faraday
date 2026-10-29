# Removes the Faraday program files and shortcuts for the current user.
# Vaults (Documents\Faraday), their backups and settings (%LOCALAPPDATA%\FaradayVault) are NOT removed.

$ErrorActionPreference = "Stop"
if (Get-Process -Name Faraday -ErrorAction SilentlyContinue) {
    throw "Faraday is running. Close it first."
}
$Target = Join-Path $env:LOCALAPPDATA "Programs\Faraday"
foreach ($lnk in @(
    (Join-Path ([Environment]::GetFolderPath("Programs")) "Faraday.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "Faraday.lnk"))) {
    if (Test-Path $lnk) { Remove-Item $lnk -Force }
}
if (Test-Path $Target) {
    # Only the program folder; it never contains vault data.
    Set-Location $env:TEMP
    Remove-Item $Target -Recurse -Force
}
Write-Host "Faraday removed. Your vaults and settings were left in place."
