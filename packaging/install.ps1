# Installs the built Faraday app for the current user (no admin rights needed).
#
#   Program files : %LOCALAPPDATA%\Programs\Faraday
#   Shortcuts     : Start Menu (and Desktop with -DesktopShortcut)
#
# Your vaults (Documents\Faraday) and settings (%LOCALAPPDATA%\FaradayVault)
# are never touched by installing, upgrading or uninstalling.

param(
    [string]$Source = (Join-Path $PSScriptRoot "..\dist\Faraday"),
    [switch]$DesktopShortcut
)
$ErrorActionPreference = "Stop"

$Source = (Resolve-Path $Source).Path
if (-not (Test-Path (Join-Path $Source "Faraday.exe"))) {
    throw "Faraday.exe not found in $Source. Run packaging\build.ps1 first."
}
if (Get-Process -Name Faraday -ErrorAction SilentlyContinue) {
    throw "Faraday is running. Close it (lock your vault first), then run the installer again."
}

$Target = Join-Path $env:LOCALAPPDATA "Programs\Faraday"
$Staging = "$Target.new"
if (Test-Path $Staging) { Remove-Item $Staging -Recurse -Force }
Copy-Item $Source $Staging -Recurse
if (Test-Path $Target) {
    $Old = "$Target.old"
    if (Test-Path $Old) { Remove-Item $Old -Recurse -Force }
    Rename-Item $Target (Split-Path $Old -Leaf)
    Rename-Item $Staging (Split-Path $Target -Leaf)
    Remove-Item $Old -Recurse -Force
} else {
    Rename-Item $Staging (Split-Path $Target -Leaf)
}
Copy-Item (Join-Path $PSScriptRoot "uninstall.ps1") (Join-Path $Target "uninstall.ps1") -Force

$Shell = New-Object -ComObject WScript.Shell
function New-Shortcut([string]$Path) {
    $lnk = $Shell.CreateShortcut($Path)
    $lnk.TargetPath = Join-Path $Target "Faraday.exe"
    $lnk.WorkingDirectory = $Target
    $lnk.IconLocation = (Join-Path $Target "Faraday.exe") + ",0"
    $lnk.Description = "Faraday offline vault by Pure Tech"
    $lnk.Save()
}
$StartMenu = Join-Path ([Environment]::GetFolderPath("Programs")) "Faraday.lnk"
New-Shortcut $StartMenu
if ($DesktopShortcut) { New-Shortcut (Join-Path ([Environment]::GetFolderPath("Desktop")) "Faraday.lnk") }

Write-Host "Faraday installed to $Target"
Write-Host "Start it from the Start Menu, or run: `"$Target\Faraday.exe`""
