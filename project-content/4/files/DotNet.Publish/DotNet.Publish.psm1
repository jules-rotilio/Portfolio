$publicDir = Join-Path -Path $PSScriptRoot -ChildPath 'Public'
if (Test-Path -Path $publicDir) {
    Get-ChildItem -Path $publicDir -Filter '*.ps1' -File | ForEach-Object {
        . $_.FullName
    }
}

# Export the functions that were loaded
$expected = @(
    'Start-DotnetPublish',
    'New-ManPage',
    'New-DebPackage',
    'Install-ManPage'
)

$available = Get-Command -CommandType Function | Select-Object -ExpandProperty Name
$toExport = $expected | Where-Object { $available -contains $_ }

if ($toExport.Count -gt 0) {
    Export-ModuleMember -Function $toExport
}
