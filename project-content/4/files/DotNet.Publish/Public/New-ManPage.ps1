<#
.SYNOPSIS
Create a section 1 man page file for a project, auto-named from the first .csproj found.

.DESCRIPTION
Generates a groff man page (.1) using a simple template. If a .csproj exists under the provided ProjectPath,
the output filename is derived from the project name (e.g., AlarmClock.csproj -> AlarmClock.1).
The function writes UTF-8 (no BOM) and returns the full path to the created man file.

.PARAMETER ProjectPath
Path to search for a .csproj file. Defaults to current directory.

.PARAMETER Version
Version string to include in the man header. Defaults to current date.

.PARAMETER OutputPath
Explicit output path for the .1 file. If omitted, the file is created in the current directory
and named after the project or folder.

.PARAMETER Author
Author string to include in the AUTHOR section.

.PARAMETER ShortDescription
One-line description used in the NAME section.

.PARAMETER LongDescription
Longer description used in the DESCRIPTION section.

.EXAMPLE
New-ManPage -ProjectPath . -Version "1.2.3" -Author "You <you@example.com>" -ShortDescription "play an audio file or Spotify link as an alarm"

.OUTPUTS
String - full path to the created man page file.

.NOTES
Designed for PowerShell Core on Linux. Overwrites existing file at OutputPath.
#>
function New-ManPage {
    [CmdletBinding()]
    param(
        [Parameter(Position = 0)]
        [string]$ProjectPath = ".",

        [Parameter(Position = 1)]
        [string]$Version = $(Get-Date -Format "yyyy.MM.dd"),

        [Parameter(Position = 2)]
        [string]$OutputPath,

        [string]$ShortDescription = "Command-line tool",
        [string]$LongDescription = ""
    )

    # Resolve project and determine base name
    $proj = Get-ChildItem -Path $ProjectPath -Filter *.csproj -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($proj) {
        $baseName = [System.IO.Path]::GetFileNameWithoutExtension($proj.Name).ToLower()
    }
    else {
        $resolved = Resolve-Path -Path $ProjectPath -ErrorAction SilentlyContinue
        if ($resolved) {
            $baseName = Split-Path -Path $resolved.ProviderPath -Leaf
        }
        else {
            $baseName = "app"
        }
    }

    if (-not $OutputPath) {
        $OutputPath = Join-Path -Path (Get-Location) -ChildPath ("{0}.1" -f $baseName)
    }

    $outDir = Split-Path -Path $OutputPath -Parent
    if ($outDir -and -not (Test-Path $outDir)) {
        New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    }

    if (-not $LongDescription) {
        $LongDescription = "$ShortDescription. See SYNOPSIS and EXAMPLES for usage."
    }

    $date = Get-Date -Format "MMMM yyyy"
    $man = @"
.TH $($baseName.ToUpper()) 1 "$date" "$baseName $Version" "User Commands"
.SH NAME
$baseName \- $ShortDescription
.SH SYNOPSIS
.B $baseName
.I <path-to-audio-file \| spotify-url>
.SH DESCRIPTION
$LongDescription
.SH OPTIONS
.TP
.B \-h, \-\-help
Show usage information.
.SH EXAMPLES
$baseName x
$baseName y
.SH AUTHOR
Jules ROTILIO
"@

    # Write file with UTF8 (no BOM)
    $resolvedOut = Resolve-Path -Path $OutputPath -ErrorAction SilentlyContinue
    if ($resolvedOut) {
        $outFile = $resolvedOut.ProviderPath
    }
    else {
        $outFile = (Join-Path -Path (Get-Location) -ChildPath (Split-Path -Path $OutputPath -Leaf))
    }

    [System.IO.File]::WriteAllBytes($outFile, [System.Text.Encoding]::UTF8.GetBytes($man))

    Write-Output $outFile
}