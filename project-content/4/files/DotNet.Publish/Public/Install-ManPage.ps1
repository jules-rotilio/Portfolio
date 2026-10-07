<#
.SYNOPSIS
Install a section 1 man page file to the system man directory and update the man database.

.DESCRIPTION
Copies a .1 man page into /usr/local/share/man/man1 (or a custom SystemManDir) using sudo,
then runs mandb to update the man database. If the target file does not exist, the function throws.
If a file already exists at the destination, use -Force to overwrite.

.PARAMETER ManFilePath
Path to the .1 man page to install (required).

.PARAMETER SystemManDir
Target system man directory. Defaults to /usr/local/share/man/man1.

.PARAMETER Force
Overwrite an existing man page at the destination.

.EXAMPLE
Install-ManPage -ManFilePath ./publish/1.2.3/Release/AlarmClock.1

.OUTPUTS
String - path to the installed man page on success.

.NOTES
Requires sudo privileges to copy into the system man directory and to run mandb.
#>
function Install-ManPage {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [string]$ManFilePath,

        [string]$SystemManDir = "/usr/local/share/man/man1",
        [switch]$Force
    )

    if (-not (Test-Path -Path $ManFilePath -PathType Leaf)) {
        throw "Man page not found: $ManFilePath"
    }

    # Ensure filename ends with .1
    if (-not ($ManFilePath -match '\.1$')) {
        throw "Provided file does not appear to be a section 1 man page (filename must end with .1)"
    }

    # Ensure target dir exists
    if (-not (Test-Path -Path $SystemManDir)) {
        Write-Host "Creating system man directory: $SystemManDir"
        & sudo mkdir -p $SystemManDir
        if ($LASTEXITCODE -ne 0) { throw "Failed to create $SystemManDir (sudo mkdir returned $LASTEXITCODE)" }
    }

    $dest = Join-Path $SystemManDir ([System.IO.Path]::GetFileName($ManFilePath))

    if ((Test-Path -Path $dest) -and -not $Force) {
        throw "A man page already exists at $dest. Use -Force to overwrite."
    }

    Write-Host "Installing man page to $dest"
    & sudo cp $ManFilePath $dest
    if ($LASTEXITCODE -ne 0) { throw "Failed to copy man page (sudo cp returned $LASTEXITCODE)" }

    & sudo mandb
    if ($LASTEXITCODE -ne 0) { throw "mandb failed with exit code $LASTEXITCODE" }

    Write-Host "Man page installed and database updated."
    return $dest
}