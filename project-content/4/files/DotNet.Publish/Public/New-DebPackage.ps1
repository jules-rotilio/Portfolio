<#
.SYNOPSIS
Create a Debian package directory layout for a binary and its man page, optionally build a .deb.

.DESCRIPTION
Creates the minimal Debian filesystem layout (DEBIAN/control, usr/bin, usr/share/man/man1),
copies the provided binary and man page into place, ensures the binary is executable, and
optionally runs dpkg-deb --build to produce a .deb file.

.PARAMETER BinaryPath
Path to the executable to package (required).

.PARAMETER ManPagePath
Path to the .1 man file to include (required).

.PARAMETER PackageName
Package name (defaults to the lowercase binary filename).

.PARAMETER Version
Package version string.

.PARAMETER Architecture
Package architecture (amd64, arm64, armhf).

.PARAMETER Maintainer
Maintainer field for control file.

.PARAMETER Description
Short description for control file.

.PARAMETER Section
Control file Section field.

.PARAMETER Priority
Control file Priority field.

.PARAMETER BuildDeb
Switch to run dpkg-deb --build and return the .deb path.

.PARAMETER OutputDirectory
Directory where the package layout (and .deb if built) will be created.

.EXAMPLE
New-DebPackage -BinaryPath ./publish/1.2.3/Release/AlarmClock -ManPagePath ./publish/1.2.3/Release/AlarmClock.1 -Version "1.2.3" -BuildDeb

.OUTPUTS
String - path to the package root directory or the built .deb file.

.NOTES
Requires dpkg-deb on the host. Overwrites any existing package directory with the same name.
#>
function New-DebPackage {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$BinaryPath,

        [Parameter(Mandatory = $true)]
        [string]$ManPagePath,

        [string[]]$AdditionalFiles,            # new: list of files to include
        [string]$DataPrefix = "usr/share",     # new: base target for data files

        [string]$PackageName,
        [string]$Version = "1.0.0",
        [ValidateSet("amd64", "arm64", "armhf")]
        [string]$Architecture = "amd64",
        [string]$Maintainer = "Jules ROTILIO <jules@rotilio.fr>",
        [string]$Description = "Command-line tool",
        [string]$Section = "utils",
        [string]$Priority = "optional",
        [switch]$BuildDeb,
        [string]$OutputDirectory = "."
    )

    # Validate inputs
    if (-not (Test-Path -Path $BinaryPath -PathType Leaf)) { throw "Binary not found: $BinaryPath" }
    if (-not (Test-Path -Path $ManPagePath -PathType Leaf)) { throw "Man page not found: $ManPagePath" }

    $binName = [System.IO.Path]::GetFileName($BinaryPath)
    if (-not $PackageName) { $PackageName = $binName.ToLower() }

    $outputRoot = (Resolve-Path -Path $OutputDirectory).ProviderPath
    $pkgDirName = "{0}_{1}_{2}" -f $PackageName, $Version, $Architecture
    $pkgRoot = Join-Path -Path $outputRoot -ChildPath $pkgDirName

    # Clean/create layout
    if (Test-Path $pkgRoot) { Remove-Item -Recurse -Force -Path $pkgRoot }
    New-Item -ItemType Directory -Path $pkgRoot -Force | Out-Null

    $usrBin = Join-Path $pkgRoot "usr/bin"
    $manDir = Join-Path $pkgRoot "usr/share/man/man1"
    $debianDir = Join-Path $pkgRoot "DEBIAN"

    New-Item -ItemType Directory -Path $usrBin -Force | Out-Null
    New-Item -ItemType Directory -Path $manDir -Force | Out-Null
    New-Item -ItemType Directory -Path $debianDir -Force | Out-Null

    # Copy files
    Copy-Item -Path $BinaryPath -Destination (Join-Path $usrBin $binName) -Force
    & chmod +x (Join-Path $usrBin $binName) 2>$null

    $manDest = Join-Path $manDir ([System.IO.Path]::GetFileName($ManPagePath))
    Copy-Item -Path $ManPagePath -Destination $manDest -Force

    # inside New-DebPackage after creating $pkgRoot and $manDir
    $pkgDataRoot = Join-Path $pkgRoot $DataPrefix
    if ($AdditionalFiles) {
        foreach ($src in $AdditionalFiles) {
            if (-not (Test-Path -Path $src -PathType Leaf)) { throw "Additional file not found: $src" }
            $fileName = [System.IO.Path]::GetFileName($src)
            $targetDir = Join-Path $pkgDataRoot $PackageName
            if (-not (Test-Path $targetDir)) { New-Item -ItemType Directory -Path $targetDir -Force | Out-Null }
            $dest = Join-Path $targetDir $fileName
            Copy-Item -Path $src -Destination $dest -Force
        }
    }


    # Create control file
    $control = @"
Package: $PackageName
Version: $Version
Section: $Section
Priority: $Priority
Architecture: $Architecture
Maintainer: $Maintainer
Description: $Description
"@

    $controlPath = Join-Path $debianDir "control"
    Set-Content -Path $controlPath -Value $control -Encoding UTF8

    Write-Host "Debian package layout created at: $pkgRoot"

    if ($BuildDeb) {
        # Build on a real Unix filesystem (avoid NTFS permission issues)
        $tmpRoot = [System.IO.Path]::GetTempPath().TrimEnd('/')
        $tmpBuildDir = Join-Path $tmpRoot ("debbuild_{0}" -f ([System.Guid]::NewGuid().ToString()))
        try {
            New-Item -ItemType Directory -Path $tmpBuildDir -Force | Out-Null

            # Copy package tree to temp build dir
            $tmpPkgRoot = Join-Path $tmpBuildDir (Split-Path -Path $pkgRoot -Leaf)
            Copy-Item -Path $pkgRoot -Destination $tmpPkgRoot -Recurse -Force

            # Ensure DEBIAN directory permissions are acceptable to dpkg-deb
            $tmpDebianDir = Join-Path $tmpPkgRoot "DEBIAN"
            if (-not (Test-Path $tmpDebianDir)) {
                throw "DEBIAN directory missing in temp package tree: $tmpDebianDir"
            }

            # Set recommended permissions
            & chmod 0755 $tmpDebianDir 2>$null
            Get-ChildItem -Path $tmpDebianDir -File -Recurse | ForEach-Object {
                & chmod 0644 $_.FullName 2>$null
            }

            # Ensure binaries are executable
            $tmpUsrBin = Join-Path $tmpPkgRoot "usr/bin"
            if (Test-Path $tmpUsrBin) {
                Get-ChildItem -Path $tmpUsrBin -File -Recurse | ForEach-Object {
                    & chmod 0755 $_.FullName 2>$null
                }
            }

            # Build .deb in temp dir
            $debFileName = "{0}_{1}_{2}.deb" -f $PackageName, $Version, $Architecture
            $tmpDebPath = Join-Path $tmpBuildDir $debFileName

            # prefer fakeroot if available
            if (Get-Command fakeroot -ErrorAction SilentlyContinue) {
                & fakeroot dpkg-deb --build $tmpPkgRoot $tmpDebPath
            }
            else {
                & dpkg-deb --build --root-owner-group $tmpPkgRoot $tmpDebPath
            }
            if ($LASTEXITCODE -ne 0) { throw "dpkg-deb failed with exit code $LASTEXITCODE" }


            # Copy .deb back to output directory
            $debFile = Join-Path -Path $outputRoot -ChildPath $debFileName
            Copy-Item -Path $tmpDebPath -Destination $debFile -Force

            Write-Host "Built .deb at: $debFile"
            Write-Output (Resolve-Path -Path $debFile).ProviderPath
        }
        finally {
            # Cleanup temp build dir if it exists
            if (Test-Path $tmpBuildDir) {
                try { Remove-Item -Recurse -Force -Path $tmpBuildDir } catch { }
            }
        }
    }
    else {
        Write-Output $pkgRoot
    }

}