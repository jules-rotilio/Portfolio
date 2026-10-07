<#
.SYNOPSIS
Publish a .NET project, bump its version, and produce versioned publish outputs.

.DESCRIPTION
Start-DotnetPublish locates the first .csproj under the current directory, reads and optionally
increments the project version (major/minor/patch), updates the .csproj, and runs
`dotnet publish` for both Debug and Release configurations. Outputs are placed under
a versioned folder structure: <PublishDir>/<Version>/{Release,Debug}.

The function can optionally generate or install a man page and prepare a Debian package layout
(if integrated with helper functions). It is intended for use on PowerShell Core running on Linux.

.PARAMETER Framework
Target framework to publish for (e.g., net10.0). Valid values: net8.0, net9.0, net10.0.

.PARAMETER Runtime
Target runtime identifier (RID) for publishing (e.g., linux-x64). Common values include:
linux-x64, linux-arm, linux-arm64, linux-musl-arm, linux-musl-arm64, win-x64, win-arm64, osx-x64, osx-arm64.

.PARAMETER PublishDir
Root directory where publish outputs will be placed. The function creates a subfolder
named after the computed version and places Release and Debug outputs there. Default: "publish".

.PARAMETER SingleFile
Boolean. When true, sets `PublishSingleFile=true` for `dotnet publish`. Default: $true.

.PARAMETER SelfContained
Boolean. When true, sets `SelfContained=true` for `dotnet publish`. Default: $false.

.PARAMETER MajorUpdate
Switch. When provided, increments the major version, resets minor and patch to 0.
This parameter is part of a mutually exclusive parameter set with MinorUpdate and PatchUpdate.

.PARAMETER MinorUpdate
Switch. When provided, increments the minor version and resets patch to 0.
This parameter is part of a mutually exclusive parameter set with MajorUpdate and PatchUpdate.

.PARAMETER PatchUpdate
Switch. When provided, increments the patch version. This parameter is part of a mutually
exclusive parameter set with MajorUpdate and MinorUpdate.

.PARAMETER InstallManPage
Switch. If set, the function will attempt to locate a section 1 man page named after the
project (e.g., AlarmClock.1) in the publish output and install it system-wide using
Install-ManPage (or by copying to /usr/local/share/man/man1 and running mandb). If no .1 file
is found, the function will throw an error.

.PARAMETER PackageDeb
Switch. If set, the function will prepare a Debian package layout for the published binary
and man page (using New-DebPackage or equivalent). Optionally the pipeline can build a .deb.

.OUTPUTS
String - Path to the versioned publish root (e.g., ./publish/1.2.3) is written to host output.
The function also writes progress and status messages to the host.

.EXAMPLE
Start-DotnetPublish -Framework net10.0 -Runtime linux-x64 -PublishDir publish -MinorUpdate

Publishes the project targeting net10.0/linux-x64, increments the minor version, updates the
.csproj, and writes outputs to publish/<new-version>/{Release,Debug}.

.EXAMPLE
Start-DotnetPublish -Framework net10.0 -Runtime linux-x64 -PublishDir publish -PatchUpdate -InstallManPage

Publishes and installs the generated or discovered AlarmClock.1 man page into the system man
directory (requires sudo).

.NOTES
- The function prefers to read and update the Version or PackageVersion element in the .csproj via XML.
  If XML parsing fails it falls back to regex-based edits.
- If the .csproj contains an unconventional version format, manual intervention may be required.
- `dotnet` must be available in PATH. `sudo`, `mandb`, and `dpkg-deb` (for packaging) are required
  for optional install/package operations.
- Designed for PowerShell Core on Linux; behavior on Windows may differ for install/package steps.
#>

function Start-DotnetPublish {
    param(
        <#
        [ValidateSet("Debug", "Release")]
        [string]$Configuration = "Release",
        #>

        [ValidateSet("net8.0", "net9.0", "net10.0")]
        [string]$Framework = "net10.0",

        [ValidateSet(
            "linux-x64",
            "linux-arm",
            "linux-arm64",
            "linux-musl-arm",
            "linux-musl-arm64",
            "win-x64",
            "win-arm64",
            "osx-x64",
            "osx-arm64"
        )]
        [string]$Runtime = "linux-x64",

        [string]$PublishDir = "publish",

        [bool]$SingleFile = $true,
        [bool]$SelfContained = $false,

        [Parameter(ParameterSetName = 'Maj', Mandatory = $true)]
        [switch]$MajorUpdate,
        [Parameter(ParameterSetName = 'Min', Mandatory = $true)]
        [switch]$MinorUpdate,
        [Parameter(ParameterSetName = 'Pat', Mandatory = $true)]
        [switch]$PatchUpdate,
        [Parameter(ParameterSetName = 'New', Mandatory = $true)]
        [switch]$FirstPublish
    )

    # locate the first csproj under the current directory
    $csproj = Get-ChildItem -Path . -Filter *.csproj -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1

    if (-not $csproj) {
        throw "No .csproj file found under the current directory."
    }

    Write-Host "Using project:" $csproj.FullName

    # read current version from csproj (try XML first, fallback to regex)
    $currentVersion = $null
    try {
        [xml]$xml = Get-Content -Path $csproj.FullName -Raw
        $versionNode = $xml.SelectSingleNode("//Project/PropertyGroup/Version")
        if (-not $versionNode) {
            $versionNode = $xml.SelectSingleNode("//Project/PropertyGroup/PackageVersion")
        }
        if ($versionNode -and $versionNode.InnerText.Trim()) {
            $currentVersion = $versionNode.InnerText.Trim()
        }
    }
    catch {
        $content = Get-Content -Path $csproj.FullName -Raw
        $m = [regex]::Match($content, '<Version>\s*(?<v>[^<]+)\s*</Version>')
        if ($m.Success) {
            $currentVersion = $m.Groups['v'].Value.Trim()
        }
        else {
            $m2 = [regex]::Match($content, '<PackageVersion>\s*(?<v>[^<]+)\s*</PackageVersion>')
            if ($m2.Success) {
                $currentVersion = $m2.Groups['v'].Value.Trim()
            }
        }
    }




    if ($null -eq $currentVersion -and $FirstPublish) {
        
        $currentVersion = "1.0.0"

        Write-Host "Current version not detected"
        Write-Host "Default version : $currentVersion"
        $newVersion = $currentVersion
    }elseif ($FirstPublish){
        Write-Host "Version detected : '$currentVersion'"
        $newVersion = $currentVersion
    }
    else {
        Write-Host "Current version detected:" $currentVersion

        # parse version parts and increment minor
        $parts = $currentVersion.Split('.')
        if ($parts.Count -eq 1) {
            $major = [int]$parts[0]
            $minor = 0
            $patch = $null
        }
        elseif ($parts.Count -eq 2) {
            $major = [int]$parts[0]
            $minor = [int]$parts[1]
            $patch = $null
        }
        elseif ($parts.Count -eq 3) {
            $major = [int]$parts[0]
            $minor = [int]$parts[1]
            $patch = [int]$parts[2]
        }
        else {
            throw [System.Exception]::new("unexpected error : `$parts.Count = $($parts.Count)")
        }

        if ($MajorUpdate) {
            $major += 1
            $minor = 0
            $patch = 0
        }
        elseif ($MinorUpdate) {
            $minor += 1
            $patch = 0
        }
        elseif ($PatchUpdate) {
            $patch += 1
        }
        $newVersion = if ($null -ne $patch) { "$major.$minor.$patch" } else { "$major.$minor" }

        Write-Host "New version will be:" $newVersion
    }
    # update csproj: prefer XML update, fallback to regex insertion/replacement
    $updated = $false
    try {
        [xml]$xml = Get-Content -Path $csproj.FullName -Raw

        $versionNode = $xml.SelectSingleNode("//Project/PropertyGroup/Version")
        if ($versionNode) {
            $versionNode.InnerText = $newVersion
            $updated = $true
        }
        else {
            $pkgNode = $xml.SelectSingleNode("//Project/PropertyGroup/PackageVersion")
            if ($pkgNode) {
                $pkgNode.InnerText = $newVersion
                $updated = $true
            }
            else {
                $pg = $xml.SelectSingleNode("//Project/PropertyGroup")
                if (-not $pg) {
                    $pg = $xml.CreateElement("PropertyGroup")
                    $xml.Project.AppendChild($pg) | Out-Null
                }
                $vElem = $xml.CreateElement("Version")
                $vElem.InnerText = $newVersion
                $pg.AppendChild($vElem) | Out-Null
                $updated = $true
            }
        }

        if ($updated) {
            $xml.Save($csproj.FullName)
            Write-Host "Updated csproj with new Version."
        }
    }
    catch {
        $content = Get-Content -Path $csproj.FullName -Raw
        if ($content -match '<Version>\s*[^<]+\s*</Version>') {
            $content = [regex]::Replace($content, '<Version>\s*[^<]+\s*</Version>', "<Version>$newVersion</Version>")
            Set-Content -Path $csproj.FullName -Value $content
            $updated = $true
            Write-Host "Replaced existing <Version> via regex."
        }
        elseif ($content -match '<PackageVersion>\s*[^<]+\s*</PackageVersion>') {
            $content = [regex]::Replace($content, '<PackageVersion>\s*[^<]+\s*</PackageVersion>', "<PackageVersion>$newVersion</PackageVersion>")
            Set-Content -Path $csproj.FullName -Value $content
            $updated = $true
            Write-Host "Replaced existing <PackageVersion> via regex."
        }
        else {
            if ($content -match '(<PropertyGroup[^>]*>)') {
                $content = [regex]::Replace($content, '(<PropertyGroup[^>]*>)', "`$1`n    <Version>$newVersion</Version>", 1)
                Set-Content -Path $csproj.FullName -Value $content
                $updated = $true
                Write-Host "Inserted <Version> into first PropertyGroup via regex."
            }
        }
    }

    if (-not $updated) {
        Write-Warning "Could not update the csproj file automatically. The new version will still be passed to dotnet publish via -p:Version."
    }

    $assemblyName = $csproj.BaseName.ToLower()


    # prepare publish directories: <PublishDir>\<Version>\Release and \Debug
    $publishRoot = Resolve-Path -Path $PublishDir -ErrorAction SilentlyContinue | ForEach-Object { $_.ProviderPath } 
    if (-not $publishRoot) {
        $publishRoot = Join-Path -Path (Get-Location) -ChildPath $PublishDir
    }
    $versionDir = Join-Path -Path $publishRoot -ChildPath $newVersion
    $releaseOut = Join-Path -Path $versionDir -ChildPath "Release"
    $debugOut = Join-Path -Path $versionDir -ChildPath "Debug"

    New-Item -ItemType Directory -Path $releaseOut -Force | Out-Null
    New-Item -ItemType Directory -Path $debugOut -Force | Out-Null

    Write-Host "Publish layout will be:"
    Write-Host "  $releaseOut"
    Write-Host "  $debugOut"

    # msbuild-friendly values
    $singleFileValue = if ($SingleFile) { "true" } else { "false" }
    $selfContainedValue = if ($SelfContained) { "true" } else { "false" }

    # publish both Debug and Release into the version directory subfolders
    foreach ($cfg in @("Debug", "Release")) {
        $outDir = if ($cfg -eq "Debug") { $debugOut } else { $releaseOut }
        Write-Host "Publishing configuration $cfg to $outDir ..."

        $_args = @(
            "publish",
            "-c", $cfg,
            "-f", $Framework,
            "-r", $Runtime,
            "-p:PublishSingleFile=$singleFileValue",
            "-p:SelfContained=$selfContainedValue",
            "-p:Version=$newVersion",
            "-p:AssemblyName=$assemblyName",
            "--property:PublishDir=$outDir"
        )

        # run dotnet publish with the constructed args
        & dotnet @_args

        if ($LASTEXITCODE -ne 0) {
            Write-Warning "dotnet publish failed for configuration $cfg (exit code $LASTEXITCODE)."
        }
        else {
            Write-Host "Published $cfg successfully."
        }
    }

    Write-Host "All done. Published version $newVersion into $versionDir"
}