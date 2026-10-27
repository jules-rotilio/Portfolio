# Builds Intercom and makes a zip to share: dist\Intercom-windows.zip, with
# Intercom.exe (icon included) and the README. Nothing to install: unzip and
# run Intercom.exe. Run from the project folder, in PowerShell:
#   powershell -ExecutionPolicy Bypass -File packaging\windows\package.ps1
$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\..\.."
cargo build --release --manifest-path "$root\Cargo.toml"
$out = "$root\dist\Intercom"
Remove-Item -Recurse -Force "$root\dist" -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $out | Out-Null
# Cargo builds into CARGO_TARGET_DIR when it is set, not target\.
$target = if ($env:CARGO_TARGET_DIR) { $env:CARGO_TARGET_DIR } else { "$root\target" }
Copy-Item "$target\release\intercom.exe" "$out\Intercom.exe"
Copy-Item "$root\README.md" "$out\README.md"
Compress-Archive -Path $out -DestinationPath "$root\dist\Intercom-windows.zip"
Write-Host "Made dist\Intercom-windows.zip. Others also need VB-Audio Virtual Cable: https://vb-audio.com/Cable/"
