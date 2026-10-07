function Export-FilesToMarkdown {
    <#
.SYNOPSIS
  Export files from a directory tree into a Markdown file with language-aware code fences,
  plus a human tree and an AI-friendly JSON tree.

.NOTES
  - Designed for PowerShell 7+ (cross-platform).
  - Avoids Add-Type; uses built-in .NET types.
  - Skips binary files by default (writes a placeholder).
  - Fixed OrderedDictionary usage and null checks.
#>

    param(
        [string]$RootPath = (Get-Location).Path,

        [string[]]$Extensions,

        [string]$OutputMarkdown,

        [int]$BinaryProbeBytes = 4096,

        [int]$MaxFileSizeMB = 50,

        [ValidateRange(0, 20)]
        [int]$Depth = 0

    )

    # ---------------------------
    # Resolve paths
    # ---------------------------
    $RootPath = (Resolve-Path -LiteralPath $RootPath).Path

    if ([string]::IsNullOrWhiteSpace($OutputMarkdown)){
        $directoryName = Split-Path -Path $RootPath -Leaf
        if ([string]::IsNullOrWhiteSpace($directoryName)){
            $directoryName = (Get-Item -LiteralPath $RootPath).Name
        }

        $OutputMarkdown = Join-Path (Get-Location).Path "$directoryName.md"
    }
    else {
        $parent = Split-Path -Path $OutputMarkdown -Parent

        if ([string]::IsNullOrWhiteSpace($parent)){
            $OutputMarkdown = Join-Path (Get-Location).Path $OutputMarkdown
        }
        else {
            $resolvedParent = (Resolve-Path -LiteralPath $parent).Path
            $OutputMarkdown = Join-Path $resolvedParent (Split-Path $OutputMarkdown -Leaf)
        }
    }

    # ---------------------------
    # Extension -> code-fence language dictionary
    # ---------------------------
    $extToLang = @{
        # .NET / C# / F#
        'cs'            = 'csharp'
        'csx'           = 'csharp'
        'fs'            = 'fsharp'
        'fsx'           = 'fsharp'
        'vb'            = 'vbnet'
        'csproj'        = 'xml'
        'fsproj'        = 'xml'
        'sln'           = 'text'
        'nuspec'        = 'xml'
        'props'         = 'xml'
        'targets'       = 'xml'
        'resx'          = 'xml'
        'dll'           = 'binary'
        'exe'           = 'binary'

        # Avalonia / XAML
        'axaml'         = 'xml'
        'xaml'          = 'xml'

        # Web / frontend
        'html'          = 'html'
        'htm'           = 'html'
        'css'           = 'css'
        'scss'          = 'scss'
        'sass'          = 'scss'
        'less'          = 'less'
        'js'            = 'javascript'
        'mjs'           = 'javascript'
        'cjs'           = 'javascript'
        'jsx'           = 'javascript'
        'ts'            = 'typescript'
        'tsx'           = 'typescript'
        'vue'           = 'html'
        'svelte'        = 'html'
        'json'          = 'json'
        'jsonc'         = 'json'
        'md'            = 'markdown'
        'mdx'           = 'markdown'
        'rst'           = 'restructuredtext'
        'adoc'          = 'asciidoc'
        'xml'           = 'xml'
        'svg'           = 'svg'

        # Server / scripting
        'ps1'           = 'powershell'
        'psm1'          = 'powershell'
        'pwsh'          = 'powershell'
        'sh'            = 'bash'
        'bash'          = 'bash'
        'zsh'           = 'bash'
        'ksh'           = 'bash'
        'bat'           = 'bat'
        'cmd'           = 'bat'
        'pl'            = 'perl'
        'php'           = 'php'
        'py'            = 'python'
        'pyw'           = 'python'
        'rb'            = 'ruby'
        'r'             = 'r'
        'jl'            = 'julia'
        'go'            = 'go'
        'java'          = 'java'
        'kt'            = 'kotlin'
        'scala'         = 'scala'
        'groovy'        = 'groovy'

        # Templates / server-side
        'cshtml'        = 'html'
        'vbhtml'        = 'html'
        'tpl'           = 'html'
        'ejs'           = 'javascript'
        'hbs'           = 'html'

        # Build / CI / packaging
        'dockerfile'    = 'dockerfile'
        'yml'           = 'yaml'
        'yaml'          = 'yaml'
        'toml'          = 'toml'
        'ini'           = 'ini'
        'cfg'           = 'ini'
        'env'           = 'text'
        'gitignore'     = 'text'
        'gitattributes' = 'text'
        'makefile'      = 'makefile'
        'mk'            = 'makefile'
        'gradle'        = 'groovy'
        'gradle.kts'    = 'kotlin'
        'pom'           = 'xml'
        'lock'          = 'text'

        # Databases / queries
        'sql'           = 'sql'
        'psql'          = 'sql'
        'sqlite'        = 'binary'
        'db'            = 'binary'
        'csv'           = 'csv'
        'tsv'           = 'csv'
        'parquet'       = 'binary'

        # Config / policy / infra
        'tf'            = 'hcl'
        'tfvars'        = 'hcl'
        'tfstate'       = 'json'
        #'yaml'     = 'yaml'    // duplicate
        #'yml'      = 'yaml'    // duplicate
        'jsonnet'       = 'json'
        'hcl'           = 'hcl'

        # Data / serialization
        #'yaml'     = 'yaml'    // duplicate
        #'yml'      = 'yaml'    // duplicate
        'msgpack'       = 'binary'
        'proto'         = 'protobuf'
        'avsc'          = 'json'
        'ndjson'        = 'json'

        # Documentation / text
        'txt'           = 'text'
        'log'           = 'text'
        'tex'           = 'latex'
        'pdf'           = 'binary'
        'doc'           = 'binary'
        'docx'          = 'binary'
        'xls'           = 'binary'
        'xlsx'          = 'binary'
        'ppt'           = 'binary'
        'pptx'          = 'binary'

        # Images / fonts / binary
        'png'           = 'binary'
        'jpg'           = 'binary'
        'jpeg'          = 'binary'
        'gif'           = 'binary'
        'webp'          = 'binary'
        'bmp'           = 'binary'
        'ico'           = 'binary'
        #'svg'      = 'svg'    // duplicate
        'ttf'           = 'binary'
        'otf'           = 'binary'
        'woff'          = 'binary'
        'woff2'         = 'binary'
        'psd'           = 'binary'

        # Certificates / keys (text)
        'pem'           = 'text'
        'crt'           = 'text'
        'cer'           = 'text'
        'key'           = 'text'
        'csr'           = 'text'

        # Source / native languages
        'c'             = 'c'
        'h'             = 'c'
        'cpp'           = 'cpp'
        'cc'            = 'cpp'
        'cxx'           = 'cpp'
        'hpp'           = 'cpp'
        'm'             = 'objc'
        'mm'            = 'objc'
        'swift'         = 'swift'
        'asm'           = 'asm'
        's'             = 'asm'
        'rs'            = 'rust'
        'erl'           = 'erlang'
        'ex'            = 'elixir'
        'exs'           = 'elixir'

        # Shaders / graphics
        'glsl'          = 'glsl'
        'vert'          = 'glsl'
        'frag'          = 'glsl'
        'hlsl'          = 'hlsl'

        # Notebooks / interactive
        'ipynb'         = 'json'    # Jupyter notebooks are JSON (may be large)

        # Misc / tooling
        #'ini'      = 'ini'    // duplicate
        'conf'          = 'text'
        'service'       = 'text'
        'desktop'       = 'ini'
        'psd1'          = 'powershell'
        'psdxml'        = 'xml'
        'xsd'           = 'xml'
        'xsl'           = 'xml'
        'xslx'          = 'xml'
        #'svg'      = 'svg'  // duplicate

        # Fallbacks / unknown
        'bin'           = 'binary'
        'dat'           = 'binary'
        'tmp'           = 'text'
        'cache'         = 'binary'
    }


    # ---------------------------
    # Normalize extensions
    # ---------------------------
    if ($Extensions -and $Extensions.Count -gt 0) {
        $NormalizedExt = $Extensions | ForEach-Object { $_.Trim().TrimStart('.') } | Select-Object -Unique
    }
    else {
        $NormalizedExt = $extToLang.Keys
    }
    $extSet = [System.Collections.Generic.HashSet[string]]::new()
    foreach ($e in $NormalizedExt) { $null = $extSet.Add($e.ToLowerInvariant()) }

    # ---------------------------
    # Helpers
    # ---------------------------
    function Test-IsBinaryFile {
        param(
            [string]$Path,
            [int]$ProbeBytes = 4096,
            [int]$MaxTextFileSizeMB = 50,
            [switch]$UseFileCommand  # optional: call `file` on Linux for extra accuracy
        )

        if (-not (Test-Path $Path -PathType Leaf)) { return $true }

        # Size guard
        $sizeMB = [math]::Round((Get-Item $Path).Length / 1MB, 2)
        if ($sizeMB -gt $MaxTextFileSizeMB) { return $true }

        # Optional: use `file` on Unix for a quick mime-type hint
        if ($UseFileCommand -and $IsLinux) {
            try {
                $mime = (& file --brief --mime-type -- "$Path") 2>$null
                if ($mime) {
                    if ($mime.StartsWith('text') -or $mime -eq 'application/json') { return $false }
                    return $true
                }
            }
            catch { }
        }

        # Read a prefix
        try {
            $fs = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
            try {
                $buffer = New-Object byte[] ( [Math]::Min($ProbeBytes, $fs.Length) )
                $read = $fs.Read($buffer, 0, $buffer.Length)
            }
            finally {
                $fs.Close(); $fs.Dispose()
            }
        }
        catch {
            return $true
        }

        # 1) Shebang -> treat as text/script
        try {
            $prefix = [System.Text.Encoding]::UTF8.GetString($buffer, 0, $read)
            if ($prefix.StartsWith('#!')) { return $false }
        }
        catch { }

        # 2) NUL byte probe (fast and reliable for many binaries)
        for ($i = 0; $i -lt $read; $i++) {
            if ($buffer[$i] -eq 0) { return $true }
        }

        # 3) UTF-8 validity probe (tolerant)
        try {
            $decoded = [System.Text.Encoding]::UTF8.GetString($buffer, 0, $read)
            if ($decoded.Contains([char]0xFFFD)) {
                # replacement char found -> try Latin1 and check for control chars
                $decoded2 = [System.Text.Encoding]::GetEncoding('iso-8859-1').GetString($buffer, 0, $read)
                if ($decoded2 -match '\p{C}') { return $true } else { return $false }
            }
            else {
                return $false
            }
        }
        catch {
            return $true
        }
    }


    function Add-ToTree {
        param($root, $relativeParts, $fileName)
        if ($null -eq $root) { throw "Add-ToTree: root is null" }
        $node = $root
        for ($i = 0; $i -lt $relativeParts.Count; $i++) {
            $part = $relativeParts[$i]
            if (-not $node.Contains($part)) {
                # create an ordered dictionary for the child
                $child = [System.Collections.Specialized.OrderedDictionary]::new()
                $child['__files'] = @()
                $node[$part] = $child
            }
            $node = $node[$part]
            if ($null -eq $node) { throw "Add-ToTree: node became null for part '$part'" }
        }
        if (-not $node.Contains('__files')) { $node['__files'] = @() }
        $node['__files'] += $fileName
    }

    function Get-HumanTreeRender {
        param($node, $prefix)
        $lines = [System.Collections.Generic.List[string]]::new()

        # directories first
        foreach ($key in $node.Keys | Where-Object { $_ -ne '__files' } | Sort-Object) {
            $lines.Add("$prefix├─ $key/")
            $child = $node[$key]
            $childLines = Get-HumanTreeRender -node $child -prefix ("$prefix│  ")
            foreach ($l in $childLines) { $lines.Add($l) }
        }

        # then files
        if ($node.Contains('__files')) {
            foreach ($f in $node['__files'] | Sort-Object) {
                $lines.Add("$prefix├─ $f")
            }
        }

        return $lines
    }

    function Get-AITreeRender {
        param($node)
        $result = [ordered]@{ 'dirs' = @(); 'files' = @() }
        foreach ($key in $node.Keys | Where-Object { $_ -ne '__files' } | Sort-Object) {
            $child = $node[$key]
            $result['dirs'] += [ordered]@{ 'name' = $key; 'children' = Get-AITreeRender -node $child }
        }
        if ($node.Contains('__files')) {
            foreach ($f in $node['__files'] | Sort-Object) {
                $result['files'] += $f
            }
        }
        return $result
    }

    # ---------------------------
    # Prepare StringBuilder and header
    # ---------------------------
    $sb = [System.Text.StringBuilder]::new()
    $null = $sb.AppendLine("# File Dump for '$RootPath'")
    $null = $sb.AppendLine("Generated on $(Get-Date -Format o)")
    $null = $sb.AppendLine()

    # ---------------------------
    # Enumerate files once
    # ---------------------------
    # Initialize treeRoot as OrderedDictionary with consistent keys
    $treeRoot = [System.Collections.Specialized.OrderedDictionary]::new()
    $treeRoot['__files'] = @()
    $treeRoot['__children'] = [System.Collections.Specialized.OrderedDictionary]::new()
    $topFiles = [System.Collections.Generic.List[string]]::new()

    $files = Get-ChildItem -Path $RootPath -Recurse -Depth $Depth -File -ErrorAction SilentlyContinue

    foreach ($file in $files) {
        $ext = $file.Extension.TrimStart('.').ToLowerInvariant()

        # Allow extensionless files to be processed (we'll classify them by content)
        if ($ext -ne '' -and -not $extSet.Contains($ext)) { continue }

        # file size guard
        $sizeMB = [math]::Round($file.Length / 1MB, 2)
        if ($sizeMB -gt $MaxFileSizeMB) {
            $null = $sb.AppendLine("## $($file.FullName)")
            $null = $sb.AppendLine()
            $null = $sb.AppendLine('```text')
            $null = $sb.AppendLine("**Skipped**: file size $sizeMB MB exceeds limit of $MaxFileSizeMB MB.")
            $null = $sb.AppendLine('```')
            $null = $sb.AppendLine()
            continue
        }

        # Build tree
        $relDir = [System.IO.Path]::GetRelativePath($RootPath, $file.DirectoryName)
        if ($relDir -eq '.') {
            $topFiles.Add($file.Name)
        }
        else {
            $parts = $relDir -split [System.IO.Path]::DirectorySeparatorChar
            if (-not $treeRoot.Contains('__children') -or $null -eq $treeRoot['__children']) {
                $treeRoot['__children'] = [System.Collections.Specialized.OrderedDictionary]::new()
            }
            Add-ToTree -root $treeRoot['__children'] -relativeParts $parts -fileName $file.Name
        }

        # Header for file
        $null = $sb.AppendLine("## $($file.FullName)")
        $null = $sb.AppendLine()

        # If extensionless, classify by content; otherwise use mapping
        if ($ext -eq '') {
            $kindInfo = Test-IsBinaryFile -Path $file.FullName -ProbeBytes $BinaryProbeBytes -MaxTextFileSizeMB $MaxFileSizeMB
            if ($kindInfo.Kind -eq 'Binary') {
                $null = $sb.AppendLine('```text')
                $null = $sb.AppendLine("**Binary or non-text file**: $($file.Name) (size: $sizeMB MB). Content omitted.")
                $null = $sb.AppendLine('```')
                $null = $sb.AppendLine()
                continue
            }
            else {
                # text: choose language hint from shebang if available, otherwise 'text'
                if ($kindInfo.ShebangLang) { $lang = $kindInfo.ShebangLang } else { $lang = 'text' }
            }
        }
        else {
            $lang = if ($extToLang.ContainsKey($ext)) { $extToLang[$ext] } else { 'text' }
        }

        # Binary detection for known extensions marked 'binary'
        $isBinary = $false
        if ($lang -eq 'binary') {
            $isBinary = $true
        }
        else {
            # For non-extensionless files, still probe for NULs as a safety net
            $isBinary = Test-IsBinaryFile -Path $file.FullName -ProbeBytes $BinaryProbeBytes
        }

        if ($isBinary) {
            $null = $sb.AppendLine('```text')
            $null = $sb.AppendLine("**Binary or non-text file**: $($file.Name) (size: $sizeMB MB). Content omitted.")
            $null = $sb.AppendLine('```')
            $null = $sb.AppendLine()
            continue
        }

        # Open fence (single-quoted to avoid backtick interpretation)
        $null = $sb.AppendLine('```' + $lang)

        try {
            $content = [System.IO.File]::ReadAllText($file.FullName)
            $null = $sb.AppendLine($content)
        }
        catch {
            $null = $sb.AppendLine("**Error reading file**: $($_.Exception.Message)")
        }

        $null = $sb.AppendLine('```')
        $null = $sb.AppendLine()
    }

    # ---------------------------
    # Render human tree
    # ---------------------------
    $null = $sb.AppendLine('## Project tree (human)')
    $null = $sb.AppendLine()
    $null = $sb.AppendLine('```text')
    foreach ($f in $topFiles | Sort-Object) { $null = $sb.AppendLine("├─ $f") }

    if ($treeRoot.Contains('__children')) {
        foreach ($dir in $treeRoot['__children'].Keys | Sort-Object) {
            $null = $sb.AppendLine("├─ $dir/")
            $childLines = Get-HumanTreeRender -node $treeRoot['__children'][$dir] -prefix "│  "
            foreach ($l in $childLines) { $null = $sb.AppendLine($l) }
        }
    }
    $null = $sb.AppendLine('```')

    $null = $sb.AppendLine()

    # ---------------------------
    # Render AI tree (JSON)
    # ---------------------------
    $null = $sb.AppendLine('## Project tree (AI-friendly JSON)')
    $null = $sb.AppendLine()

    $aiRoot = [ordered]@{ 'dirs' = @(); 'files' = @() }
    foreach ($f in $topFiles | Sort-Object) { $aiRoot['files'] += $f }
    if ($treeRoot.Contains('__children')) {
        foreach ($dir in $treeRoot['__children'].Keys | Sort-Object) {
            $aiRoot['dirs'] += [ordered]@{ 'name' = $dir; 'children' = Get-AITreeRender -node $treeRoot['__children'][$dir] }
        }
    }

    $aiJson = $aiRoot | ConvertTo-Json -Depth 20
    $null = $sb.AppendLine('```json')
    $null = $sb.AppendLine($aiJson)
    $null = $sb.AppendLine('```')
    $null = $sb.AppendLine()

    # ---------------------------
    # Final write (UTF8 without BOM)
    # ---------------------------
    [System.IO.File]::WriteAllText($OutputMarkdown, $sb.ToString(), [System.Text.Encoding]::UTF8)

    # Get file info
    $fileInfo = Get-Item -LiteralPath $OutputMarkdown

    # Size in bytes
    $sizeBytes = $fileInfo.Length

    function Format-Size {
        param([long]$Bytes)
        if ($Bytes -ge 1GB) { "{0:N2} GB" -f ($Bytes / 1GB) }
        elseif ($Bytes -ge 1MB) { "{0:N2} MB" -f ($Bytes / 1MB) }
        elseif ($Bytes -ge 1KB) { "{0:N2} KB" -f ($Bytes / 1KB) }
        else { "$Bytes bytes" }
    }


    # Print
    Write-Host "Markdown file created at: $OutputMarkdown"
    Write-Host "Wrote $([Regex]::Matches($sb.ToString(), [Environment]::NewLine).Count + 1) Lines."
    Write-Host "Size (bytes): $(Format-Size $sizeBytes)"

}

function Import-ProjectFromMarkdown {
    <#
    .SYNOPSIS
        Reconstructs a full project directory from a Markdown file previously
        generated by Export-FilesToMarkdown or by AI.

    .DESCRIPTION
        This function performs the *reverse operation* of a project-to-Markdown
        exporter. It reads a Markdown file that contains:

            - File paths as section headers (## <full path>)
            - Code fences containing the file contents
            - Optional placeholders for binary files

        The function parses each file block, recreates the directory structure
        under a new root folder, and writes each file back to disk.

        This allows a project to be:
            - Exported to a single Markdown file
            - Shared, versioned, or fed to an AI
            - Reconstructed later with full fidelity (except binaries)

        This is useful for:
            - AI-assisted code review
            - Project snapshots
            - Archival
            - Reversible documentation
            - Rebuilding a project from a single portable file

    .PARAMETER MarkdownPath
        Path to the Markdown file created by Export-FilesToMarkdown.

    .PARAMETER OutputRoot
        Directory where the reconstructed project will be created.

    .NOTES
        - Binary files are restored as empty placeholders because the exporter
          does not embed binary content.
        - The Markdown format must match the structure produced by the exporter.
        - This function intentionally ignores the language tag in code fences,
          because file contents are restored verbatim.

    #>

    param(
        [Parameter(Mandatory = $true)]
        [string]$MarkdownPath,

        [Parameter(Mandatory = $true)]
        [string]$OutputRoot,

        [Switch]$Force
    )

    if ((Test-Path $OutputRoot) -and -not $Force) {
        throw "Output directory already exists. Use -Force to overwrite."
    }

    # Ensure the Markdown file exists before proceeding.
    if (-not (Test-Path $MarkdownPath)) {
        throw "Markdown file not found: $MarkdownPath"
    }


    # Read the entire Markdown file as a single string.
    # This allows multi-line regex parsing of code blocks.
    $content = Get-Content -Raw -Path $MarkdownPath

    # Regex pattern that matches each exported file block.
    # The exporter emits blocks like:
    #
    #   ## C:\path\to\file.txt
    #   ```powershell
    #   <file content>
    #   ```
    #
    # We capture:
    #   - path  → the full file path
    #   - lang  → the code fence language (not used, but kept for compatibility)
    #   - body  → the file contents
    #
    $pattern = '(?ms)##\s+(?<path>.+?)\s+```(?<lang>[^\r\n]*)\s+(?<body>.*?)```'

    # Run the regex and collect all file blocks.
    $_matches = [regex]::Matches($content, $pattern)

    if ($_matches.Count -eq 0) {
        Write-Warning "No file blocks found. The Markdown format may be invalid."
    }


    foreach ($m in $_matches) {

        # Extract the full original file path.
        # This is used to reconstruct the relative directory structure.
        $fullPath = $m.Groups['path'].Value.Trim()
        
        # OS‑specific path normalization
        if ($IsWindows) {
            # Convert escaped backslashes to single backslashes
            $fullPath = $fullPath -replace '\\\\', '\'
        }
        elseif ($IsLinux) {
            # Convert Windows-style backslashes to forward slashes
            $fullPath = $fullPath -replace '\\', '/'
        }

        #$lang     = $m.Groups['lang'].Value.Trim()

        # Extract the file contents inside the code fence.
        $body = $m.Groups['body'].Value
        
        # Normalize line endings only on Windows
        if ($IsWindows) {
            $body = $body -replace "`n", "`r`n"
        }

        # Split the original path into directory and filename.
        $fileName = Split-Path $fullPath -Leaf
        $dirName = Split-Path $fullPath -Parent

        # Convert the original absolute path into a relative path.
        # This removes drive letters (e.g., "C:\") and leading slashes.
        # OS‑specific relative path extraction
        if ($IsWindows) {
            # Remove drive letter and leading backslashes
            $relative = $dirName -replace '^[A-Za-z]:', '' -replace '^\\', ''
        }
        elseif ($IsLinux) {
            # Remove leading slash from absolute Linux paths
            $relative = $dirName -replace '^/', ''
        }

        # Re-root the path under the new output directory.
        $targetDir = Join-Path $OutputRoot $relative
        $targetFile = Join-Path $targetDir $fileName

        # Ensure the directory exists before writing the file.
        if (-not (Test-Path $targetDir)) {
            New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
        }

        # If the exporter marked this file as binary, we cannot restore it.
        # Instead, create an empty placeholder so the structure remains intact.
        if ($body -match '\*\*Binary or non-text file\*\*') {
            Set-Content -Path $targetFile -Value "" -Encoding utf8
            continue
        }

        # Write the file contents exactly as they appeared in the Markdown.
        Set-Content -Path $targetFile -Value $body -Encoding utf8 -NoNewline
    }

    Write-Host "Project reconstructed at: $OutputRoot"
}



New-Alias -Name epftmd -Value Export-FilesToMarkdown
New-Alias -Name ippfmd -Value Import-ProjectFromMarkdown

Export-ModuleMember -Function Export-FilesToMarkdown, Import-ProjectFromMarkdown -Alias epftmd, ippfmd