function Repair-MediaFileExtensions {
    [CmdletBinding()]
    param(
        [Parameter(Position = 0)]
        [string]$Path = (Get-Location).Path,

        [switch]$Recurse
    )

    # MIME types commonly used for media files.
    $mimeToExtension = @{
        # Images
        'image/avif'                    = @('.avif')
        'image/bmp'                     = @('.bmp')
        'image/gif'                     = @('.gif')
        'image/heic'                    = @('.heic')
        'image/jpeg'                    = @('.jpg', '.jpeg')
        'image/png'                     = @('.png')
        'image/svg+xml'                 = @('.svg')
        'image/tiff'                    = @('.tif')
        'image/webp'                    = @('.webp')
        'image/x-icon'                  = @('.ico')

        # Additional image types
        'image/jp2'                     = @('.jp2')
        'image/jpg'                     = @('.jpg', '.jpeg')
        'image/jpm'                     = @('.jpm')
        'image/jpx'                     = @('.jpx')
        'image/pjpeg'                   = @('.jpg', '.jpeg')
        'image/vnd.adobe.photoshop'     = @('.psd')
        'image/x-adobe-dng'             = @('.dng')
        'image/x-canon-cr2'             = @('.cr2')
        'image/x-nikon-nef'             = @('.nef')
        'image/x-png'                   = @('.png')
        'image/x-portable-anymap'       = @('.pnm')
        'image/x-portable-bitmap'       = @('.pbm')
        'image/x-portable-graymap'      = @('.pgm')
        'image/x-portable-pixmap'       = @('.ppm')
        'image/x-sony-arw'              = @('.arw')
        'image/x-xcf'                   = @('.xcf')

        # Video
        'video/3gpp'                    = @('.3gp')
        'video/mp4'                     = @('.mp4')
        'video/mpeg'                    = @('.mpeg')
        'video/quicktime'               = @('.mov')
        'video/webm'                    = @('.webm')
        'video/x-flv'                   = @('.flv')
        'video/x-matroska'              = @('.mkv')
        'video/x-msvideo'               = @('.avi')

        # Additional video types
        'application/vnd.apple.mpegurl' = @('.m3u8')
        'video/avi'                     = @('.avi')
        'video/dvd'                     = @('.vob')
        'video/matroska'                = @('.mkv')
        'video/mp2t'                    = @('.ts')
        'video/ogg'                     = @('.ogv')
        'video/vnd.dlna.mpeg-tts'       = @('.m2ts')
        'video/vnd.rn-realvideo'        = @('.rv')
        'video/x-f4v'                   = @('.f4v')
        'video/x-m2ts'                  = @('.m2ts')
        'video/x-m4v'                   = @('.m4v', '.mp4')
        'video/x-matroska-3d'           = @('.mk3d')
        'video/x-mjpeg'                 = @('.mjpg')
        'video/x-mpegurl'               = @('.m3u8')
        'video/x-ms-asf'                = @('.asf')
        'video/x-ms-vob'                = @('.vob')
        'video/x-ms-wmv'                = @('.wmv')
        'video/x-ogm'                   = @('.ogm')
        'video/x-realvideo'             = @('.rv')
        'video/x-sgi-movie'             = @('.movie')
        'video/x-theora'                = @('.ogv')
        'video/x-vid'                   = @('.vid')


        # Audio
        'audio/aac'                     = @('.aac')
        'audio/flac'                    = @('.flac')
        'audio/mp4'                     = @('.m4a')
        'audio/mpeg'                    = @('.mp3')
        'audio/ogg'                     = @('.ogg')
        'audio/wav'                     = @('.wav')
        'audio/webm'                    = @('.weba')
        'audio/x-ms-wma'                = @('.wma')
        'audio/x-wav'                   = @('.wav')

        # Additional audio types
        'audio/aiff'                    = @('.aiff')
        'audio/basic'                   = @('.au')
        'audio/m4a'                     = @('.m4a')
        'audio/mp3'                     = @('.mp3')
        'audio/opus'                    = @('.opus')
        'audio/vnd.dts.hd'              = @('.dtshd')
        'audio/vnd.dts'                 = @('.dts')
        'audio/vorbis'                  = @('.ogg')
        'audio/x-aac'                   = @('.aac')
        'audio/x-aiff'                  = @('.aiff')
        'audio/x-flac'                  = @('.flac')
        'audio/x-m4a'                   = @('.m4a')
        'audio/x-matroska'              = @('.mka')
        'audio/x-mpeg'                  = @('.mp3')
        'audio/x-musepack'              = @('.mpc')
        'audio/x-ogg'                   = @('.ogg')
    }

    
    try {
        $resolvedPath = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    }
    catch {
        throw "Directory not found: $Path"
    }

    if (-not (Test-Path -LiteralPath $resolvedPath -PathType Container)) {
        throw "'$resolvedPath' is not a directory."
    }

    # Build parameters dynamically so -Recurse is optional.
    $getChildItemParameters = @{
        LiteralPath = $resolvedPath
        File        = $true
    }

    if ($Recurse) {
        $getChildItemParameters.Recurse = $true
    }

    foreach ($file in Get-ChildItem @getChildItemParameters) {
        $mimeType = (& file --brief --mime-type -- $file.FullName 2>$null).Trim()

        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($mimeType)) {
            Write-Warning "Could not determine the type of '$($file.FullName)'."
            continue
        }

        # Ignore non-media files.
        if ($mimeType -notmatch '^(image|video|audio)/') {
            continue
        }

        if (-not $mimeToExtension.ContainsKey($mimeType)) {
            Write-Host "Skipped: $($file.FullName) [$mimeType - no extension mapping]"
            continue
        }

        $validExtensions = @($mimeToExtension[$mimeType])
        $actualExtension = $file.Extension.ToLowerInvariant()

        if ($validExtensions -contains $actualExtension) {
            Write-Host "OK:     $($file.FullName)"
            continue
        }

        $expectedExtension = $validExtensions[0]

        $baseName = [System.IO.Path]::GetFileNameWithoutExtension($file.Name)
        $newName = $baseName + $expectedExtension
        $newPath = Join-Path -Path $file.DirectoryName -ChildPath $newName

        if (Test-Path -LiteralPath $newPath) {
            Write-Warning "Skipped '$($file.FullName)': '$newName' already exists."
            continue
        }

        Write-Host ""
        Write-Host "File:      $($file.FullName)"
        Write-Host "Detected:  $mimeType"
        Write-Host "Current:   $actualExtension"
        Write-Host "Suggested: $newName"

        $answer = Read-Host "Rename this file? [Y/n]"

        if ($answer -eq [string]::Empty -or $answer -match '^(y|yes)$') {
            try {
                Rename-Item `
                    -LiteralPath $file.FullName `
                    -NewName $newName `
                    -ErrorAction Stop

                Write-Host "Renamed to: $newName" -ForegroundColor Green
            }
            catch {
                Write-Warning "Could not rename '$($file.FullName)': $_"
            }
        }
        else {
            Write-Host "Skipped."
        }
    }
}


<# Register-ArgumentCompleter -CommandName Get-ApprovedVerb.ps1 `
    -ParameterName Category `
    -ScriptBlock {
        param($commandName, $parameterName, $wordToComplete, $commandAst, $fakeBoundParams)

        $JsonPath = "/home/jules/.local/bin/Data/approved-verbs.json"
        if (Test-Path $JsonPath) {
            $RawData = Get-Content $JsonPath -Raw | ConvertFrom-Json
            $RawData.Category |
                Sort-Object -Unique |
                Where-Object { $_ -like "$wordToComplete*" } |
                ForEach-Object {
                    [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
                }
        }
    } #>


function Get-MediaInfo {
    [CmdletBinding()]
    param(
        [Parameter(
            Mandatory, 
            Position = 0,
            ValueFromPipeline,
            ValueFromPipelineByPropertyName
        )]
        [object]$Path,

        [string]$FfprobePath = 'ffprobe'
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "File not found: $Path"
    }

    $resolvedPath = (Resolve-Path -LiteralPath $Path).Path

    $arguments = @(
        '-v', 'error',
        '-show_entries',
        'format=filename,format_name,format_long_name,duration,size,bit_rate,probe_score:stream=index,codec_type,codec_name,codec_long_name,profile,width,height,display_aspect_ratio,pix_fmt,color_space,color_transfer,color_primaries,field_order,r_frame_rate,avg_frame_rate,bit_rate,channels,channel_layout,sample_rate,language,title',
        '-of', 'json',
        '--',
        $resolvedPath
    )

    $json = & $FfprobePath @arguments 2>$null

    if ($LASTEXITCODE -ne 0 -or -not $json) {
        throw "ffprobe failed for: $resolvedPath. Make sure ffprobe is installed and in PATH."
    }

    $probe = $json -join "`n" | ConvertFrom-Json

    function Convert-ToDouble($Value) {
        if ($null -eq $Value -or $Value -eq '') {
            return $null
        }

        try {
            return [double]::Parse(
                [string]$Value,
                [Globalization.CultureInfo]::InvariantCulture
            )
        }
        catch {
            return $null
        }
    }

    function Convert-Fraction($Value) {
        if ($null -eq $Value -or $Value -notmatch '^(\d+)/(\d+)$') {
            return $null
        }

        $numerator = Convert-ToDouble $matches[1]
        $denominator = Convert-ToDouble $matches[2]

        if ($denominator -eq 0) {
            return $null
        }

        return [math]::Round($numerator / $denominator, 3)
    }

    function Convert-Bytes($Value) {
        $bytes = Convert-ToDouble $Value

        if ($null -eq $bytes) {
            return $null
        }

        if ($bytes -ge 1GB) {
            return '{0:N2} GB' -f ($bytes / 1GB)
        }

        if ($bytes -ge 1MB) {
            return '{0:N2} MB' -f ($bytes / 1MB)
        }

        return '{0:N0} bytes' -f $bytes
    }

    function Convert-Duration($Value) {
        $seconds = Convert-ToDouble $Value

        if ($null -eq $seconds) {
            return $null
        }

        return [TimeSpan]::FromSeconds($seconds)
    }

    $streams = @($probe.streams)
    $format = $probe.format

    $video = @(
        $streams |
        Where-Object codec_type -eq 'video' |
        ForEach-Object {
            [pscustomobject]@{
                Index          = $_.index
                Codec          = $_.codec_name
                CodecName      = $_.codec_long_name
                Profile        = $_.profile
                Width          = $_.width
                Height         = $_.height
                AspectRatio    = $_.display_aspect_ratio
                PixelFormat    = $_.pix_fmt
                FrameRate      = Convert-Fraction $_.avg_frame_rate
                FrameRateRaw   = $_.avg_frame_rate
                BitrateKbps    = [math]::Round((Convert-ToDouble $_.bit_rate) / 1000, 0)
                ColorSpace     = $_.color_space
                ColorTransfer  = $_.color_transfer
                ColorPrimaries = $_.color_primaries
                FieldOrder     = $_.field_order
                Language       = $_.tags.language
                Title          = $_.tags.title
            }
        }
    )

    $audio = @(
        $streams |
        Where-Object codec_type -eq 'audio' |
        ForEach-Object {
            [pscustomobject]@{
                Index         = $_.index
                Codec         = $_.codec_name
                CodecName     = $_.codec_long_name
                Profile       = $_.profile
                Channels      = $_.channels
                ChannelLayout = $_.channel_layout
                SampleRateHz  = Convert-ToDouble $_.sample_rate
                BitrateKbps   = [math]::Round((Convert-ToDouble $_.bit_rate) / 1000, 0)
                Language      = $_.tags.language
                Title         = $_.tags.title
            }
        }
    )

    $subtitles = @(
        $streams |
        Where-Object codec_type -eq 'subtitle' |
        ForEach-Object {
            [pscustomobject]@{
                Index    = $_.index
                Codec    = $_.codec_name
                Language = $_.tags.language
                Title    = $_.tags.title
            }
        }
    )

    [pscustomobject]@{
        File      = [pscustomobject]@{
            Path      = $resolvedPath
            Name      = [IO.Path]::GetFileName($resolvedPath)
            Extension = [IO.Path]::GetExtension($resolvedPath)
        }

        Format    = [pscustomobject]@{
            Name        = $format.format_name
            Description = $format.format_long_name
            Duration    = Convert-Duration $format.duration
            Size        = Convert-Bytes $format.size
            SizeBytes   = Convert-ToDouble $format.size
            BitrateKbps = [math]::Round((Convert-ToDouble $format.bit_rate) / 1000, 0)
            ProbeScore  = $format.probe_score
        }

        Video     = $video
        Audio     = $audio
        Subtitles = $subtitles
    }
}


function Resolve-MediaFile {
    [CmdletBinding()]
    param (
        [Parameter(Mandatory)]
        [object] $InputObject
    )

    $inputPath = if ($InputObject -is [System.IO.FileInfo]) {
        $InputObject.FullName
    }
    else {
        [string]$InputObject
    }

    $file = Get-Item -LiteralPath $inputPath -ErrorAction Stop

    if ($file -isnot [System.IO.FileInfo]) {
        throw "'$inputPath' is not a file."
    }

    return $file
}

function Get-MediaDuration {
    [CmdletBinding()]
    param (
        [Parameter(Mandatory)]
        [System.IO.FileInfo] $InputFile
    )

    if (-not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
        throw "ffprobe was not found in PATH."
    }

    $durationText = & ffprobe `
        -v error `
        -show_entries format=duration `
        -of default=noprint_wrappers=1:nokey=1 `
        $InputFile.FullName 2>$null

    $durationText = ($durationText | Out-String).Trim()

    [double] $duration = 0

    $parsed = [double]::TryParse(
        $durationText,
        [Globalization.NumberStyles]::Float,
        [Globalization.CultureInfo]::InvariantCulture,
        [ref] $duration
    )

    if (
        $LASTEXITCODE -ne 0 -or
        -not $parsed -or
        $duration -le 0
    ) {
        throw "Could not determine the duration of '$($InputFile.FullName)'."
    }

    return $duration
}



function Invoke-FFmpeg {
    [CmdletBinding()]
    param (
        [Parameter(Mandatory)]
        [System.IO.FileInfo] $InputFile,

        [System.IO.FileInfo[]] $AdditionalInputFiles = @(),

        [Parameter(Mandatory)]
        [string] $OutputPath,

        [Parameter(Mandatory)]
        [string[]] $Arguments,

        [switch] $Force
    )

    if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
        throw "ffmpeg was not found in PATH."
    }

    $outputDirectory = Split-Path -Parent $OutputPath

    if (-not (Test-Path -LiteralPath $outputDirectory)) {
        New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    }

    <# if ((Test-Path -LiteralPath $OutputPath) -and -not $Force) {
        throw "Output file '$OutputPath' already exists. Use -Force to overwrite it."
    } #>

    $ffmpegArguments = @()

    if ($Force) {
        $ffmpegArguments += '-y'
    }
    else {
        $ffmpegArguments += '-n'
    }

    $ffmpegArguments += '-i'
    $ffmpegArguments += $InputFile.FullName
    foreach ($additionalInputFile in $AdditionalInputFiles) {
        $ffmpegArguments += '-i'
        $ffmpegArguments += $additionalInputFile.FullName
    }
    $ffmpegArguments += $Arguments
    $ffmpegArguments += $OutputPath

    & ffmpeg @ffmpegArguments

    if ($LASTEXITCODE -ne 0) {
        throw "ffmpeg failed while processing '$($InputFile.FullName)'."
    }

    Get-Item -LiteralPath $OutputPath
}


function Merge-VideoAudio {
    [CmdletBinding()]
    param (
        [Parameter(Mandatory, Position = 0)]
        [object] $VideoInputObject,

        [Parameter(Mandatory, Position = 1)]
        [object] $AudioInputObject,

        [Parameter(Position = 2)]
        [string] $OutputPath,

        [switch] $Force
    )

    $videoFile = Resolve-MediaFile $VideoInputObject
    $audioFile = Resolve-MediaFile $AudioInputObject

    if (-not $OutputPath) {
        $OutputPath = Join-Path $videoFile.DirectoryName "$($videoFile.BaseName)_with_audio.mp4"
    }

    $OutputPath = [System.IO.Path]::GetFullPath($OutputPath)
    $pathComparison = if ([System.IO.Path]::DirectorySeparatorChar -eq '\') {
        [StringComparison]::OrdinalIgnoreCase
    }
    else {
        [StringComparison]::Ordinal
    }

    if (
        [string]::Equals($OutputPath, $videoFile.FullName, $pathComparison) -or
        [string]::Equals($OutputPath, $audioFile.FullName, $pathComparison)
    ) {
        throw "The output path must be different from both input files."
    }

    Invoke-FFmpeg `
        -InputFile $videoFile `
        -AdditionalInputFiles @($audioFile) `
        -OutputPath $OutputPath `
        -Arguments @(
        '-map', '0:v:0',
        '-map', '1:a:0',
        '-c:v', 'copy',
        '-c:a', 'aac',
        '-b:a', '192k'
    ) `
        -Force:$Force
}


function Get-VideoDimensions {
    [CmdletBinding()]
    param (
        [Parameter(Mandatory)]
        [System.IO.FileInfo] $InputFile
    )

    if (-not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
        throw "ffprobe was not found in PATH."
    }

    $dimensions = & ffprobe `
        -v error `
        -select_streams v:0 `
        -show_entries stream=width, height `
        -of csv=p=0:s=x `
        $InputFile.FullName 2>$null

    $dimensions = ($dimensions | Out-String).Trim()

    if ($LASTEXITCODE -ne 0 -or $dimensions -notmatch '^(\d+)x(\d+)$') {
        throw "Could not determine video dimensions for '$($InputFile.FullName)'."
    }

    [pscustomobject]@{
        Width  = [int]$Matches[1]
        Height = [int]$Matches[2]
    }
}


function ConvertTo-GIF {
    [CmdletBinding()]
    param (
        [Parameter(
            Mandatory,
            Position = 0,
            ValueFromPipeline,
            ValueFromPipelineByPropertyName
        )]
        [object] $InputObject,

        [ValidateRange(1, 4096)]
        [int] $Width = 320,

        [ValidateRange(2, 256)]
        [int] $MaxColors = 100,

        [ValidateRange(1, 60)]
        [int] $FPS = 24,

        [string] $OutputDirectory,

        [switch] $Force
    )

    process {
        $file = Resolve-MediaFile $InputObject
        $dimensions = Get-VideoDimensions $file

        $height = [math]::Round(
            $Width * $dimensions.Height / $dimensions.Width
        )

        $directory = if ($OutputDirectory) {
            $OutputDirectory
        }
        else {
            $file.DirectoryName
        }

        $outputName = '{0}_{1}x{2}_{3}fps_{4}colors.gif' -f `
            $file.BaseName,
        $Width,
        $height,
        $FPS,
        $MaxColors

        $outputPath = Join-Path $directory $outputName

        $filter = @(
            "fps=$FPS"
            "scale=${Width}:-1:flags=lanczos"
            "split[s0][s1]"
            "[s0]palettegen=stats_mode=diff:max_colors=$MaxColors[p]"
            "[s1][p]paletteuse=dither=sierra2_4a"
        ) -join ','

        Invoke-FFmpeg `
            -InputFile $file `
            -OutputPath $outputPath `
            -Arguments @(
            '-vf', $filter,
            '-gifflags', '+offsetting+transdiff',
            '-loop', '0'
        ) `
            -Force:$Force
    }
}

function ConvertTo-GIFSegment {
    [CmdletBinding()]
    param (
        [Parameter(Mandatory)]
        [System.IO.FileInfo] $InputFile,

        [Parameter(Mandatory)]
        [string] $OutputPath,

        [Parameter(Mandatory)]
        [double] $StartSeconds,

        [Parameter(Mandatory)]
        [double] $DurationSeconds,

        [Parameter(Mandatory)]
        [int] $Width,

        [Parameter(Mandatory)]
        [int] $FPS,

        [Parameter(Mandatory)]
        [int] $MaxColors,

        [switch] $Force
    )

    $filter = @(
        "fps=$FPS"
        "scale=${Width}:-1:flags=lanczos"
        "split[s0][s1]"
        "[s0]palettegen=stats_mode=diff:max_colors=$MaxColors[p]"
        "[s1][p]paletteuse=dither=sierra2_4a"
    ) -join ','

    Invoke-FFmpeg `
        -InputFile $InputFile `
        -OutputPath $OutputPath `
        -Arguments @(
        '-ss', $StartSeconds,
        '-t', $DurationSeconds,
        '-vf', $filter,
        '-gifflags', '+offsetting+transdiff',
        '-loop', '0'
    ) `
        -Force:$Force
}


function ConvertTo-MP4 {
    [CmdletBinding()]
    param (
        [Parameter(
            Mandatory,
            Position = 0,
            ValueFromPipeline,
            ValueFromPipelineByPropertyName
        )]
        [object] $InputObject,

        [string] $OutputDirectory,

        [ValidateRange(0, 51)]
        [int] $CRF = 23,

        [ValidateSet('ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow')]
        [string] $Preset = 'medium',

        [switch] $Force
    )

    process {
        $file = Resolve-MediaFile $InputObject

        $directory = if ($OutputDirectory) {
            $OutputDirectory
        }
        else {
            $file.DirectoryName
        }

        $outputPath = Join-Path $directory "$($file.BaseName).mp4"

        Invoke-FFmpeg `
            -InputFile $file `
            -OutputPath $outputPath `
            -Arguments @(
            '-c:v', 'libx264',
            '-preset', $Preset,
            '-crf', $CRF,
            '-c:a', 'aac',
            '-b:a', '192k',
            '-movflags', '+faststart'
        ) `
            -Force:$Force
    }
}


function ConvertTo-PNG {
    [CmdletBinding()]
    param (
        [Parameter(
            Mandatory,
            Position = 0,
            ValueFromPipeline,
            ValueFromPipelineByPropertyName
        )]
        [object] $InputObject,

        [string] $OutputDirectory,

        [switch] $Force
    )

    process {
        [System.IO.FileInfo] $file = Resolve-MediaFile $InputObject

        [string] $directory = if ($OutputDirectory) {
            $OutputDirectory
        }
        else {
            $file.DirectoryName
        }

        [string] $outputPath = Join-Path $directory "$($file.BaseName).png"

        Invoke-FFmpeg `
            -InputFile $file `
            -OutputPath $outputPath `
            -Arguments @(
            #'-f', 'image2',
            '-update', '1',
            '-frames:v', '1',
            '-c:v', 'png'
        ) `
            -Force:$Force

    }
}


function ConvertTo-JPG {
    [CmdletBinding()]
    param (
        [Parameter(
            Mandatory,
            Position = 0,
            ValueFromPipeline,
            ValueFromPipelineByPropertyName
        )]
        [object] $InputObject,

        [string] $OutputDirectory,

        [ValidateRange(2, 31)]
        [int] $Quality = 2,

        [Parameter()]
        [ValidateSet('libjpeg-turbo', 'libjpeg', 'mjpeg')]
        [string] $Encoder = 'libjpeg-turbo',

        [switch] $Force
    )

    process {
        $file = Resolve-MediaFile $InputObject

        $directory = if ($OutputDirectory) {
            $OutputDirectory
        }
        else {
            $file.DirectoryName
        }

        $outputPath = Join-Path $directory "$($file.BaseName).jpg"

        Invoke-FFmpeg `
            -InputFile $file `
            -OutputPath $outputPath `
            -Arguments @(
            '-frames:v', '1',
            '-c:v', $Encoder,
            '-q:v', $Quality
        ) `
            -Force:$Force
    }
}

function ConvertTo-WEBP {
    [CmdletBinding()]
    param (
        [Parameter(
            Mandatory,
            Position = 0,
            ValueFromPipeline,
            ValueFromPipelineByPropertyName
        )]
        [object] $InputObject,

        [ValidateRange(1, 4096)]
        [int] $Width = 0,

        [ValidateRange(1, 60)]
        [int] $FPS = 24,

        [ValidateRange(0, 100)]
        [int] $Quality = 80,

        [string] $OutputDirectory,

        [switch] $Force
    )

    process {
        $file = Resolve-MediaFile $InputObject
        $ext = $file.Extension.ToLowerInvariant()

        $directory = if ($OutputDirectory) { $OutputDirectory } else { $file.DirectoryName }

        # Determine if input is an image
        $isImage = $ext -in @('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp')

        #
        # Determine dimensions for naming
        #
        if ($isImage) {
            # ffprobe is not needed for static images
            if ($Width -gt 0) {
                # Height will be computed by FFmpeg, but we approximate using original ratio
                $imgInfo = Get-VideoDimensions $file
                $scaledHeight = [math]::Round($Width * $imgInfo.Height / $imgInfo.Width)
                $dimText = "${Width}x${scaledHeight}"
            }
            else {
                $imgInfo = Get-VideoDimensions $file
                $dimText = "${imgInfo.Width}x${imgInfo.Height}"
            }

            $outputName = "{0}_{1}_q{2}.webp" -f $file.BaseName, $dimText, $Quality
        }
        else {
            # Video → animated WEBP
            $vidInfo = Get-VideoDimensions $file

            if ($Width -gt 0) {
                $scaledHeight = [math]::Round($Width * $vidInfo.Height / $vidInfo.Width)
                $dimText = "${Width}x${scaledHeight}"
            }
            else {
                $dimText = "${vidInfo.Width}x${vidInfo.Height}"
            }

            $outputName = "{0}_{1}_{2}fps_q{3}_anim.webp" -f $file.BaseName, $dimText, $FPS, $Quality
        }

        $outputPath = Join-Path $directory $outputName

        #
        # Build FFmpeg arguments
        #
        $ffArgs = @()

        if ($isImage) {
            if ($Width -gt 0) {
                $ffArgs += '-vf'
                $ffArgs += "scale=${Width}:-1:flags=lanczos"
            }

            $ffArgs += @(
                '-frames:v', '1',
                '-c:v', 'libwebp',
                '-quality', $Quality
            )
        }
        else {
            if ($Width -gt 0) {
                $ffArgs += '-vf'
                $ffArgs += "fps=$FPS,scale=${Width}:-1:flags=lanczos"
            }
            else {
                $ffArgs += '-vf'
                $ffArgs += "fps=$FPS"
            }

            $ffArgs += @(
                '-c:v', 'libwebp_anim',
                '-quality', $Quality,
                '-loop', '0'
            )
        }

        Invoke-FFmpeg `
            -InputFile $file `
            -OutputPath $outputPath `
            -Arguments $ffArgs `
            -Force:$Force
    }
}





function ConvertTo-MP3 {
    [CmdletBinding()]
    param (
        [Parameter(
            Mandatory,
            Position = 0,
            ValueFromPipeline,
            ValueFromPipelineByPropertyName
        )]
        [object] $InputObject,

        [string] $OutputDirectory,

        [ValidateRange(0, 9)]
        [int] $Quality = 2,

        [switch] $Force
    )

    process {
        $file = Resolve-MediaFile $InputObject

        $directory = if ($OutputDirectory) {
            $OutputDirectory
        }
        else {
            $file.DirectoryName
        }

        $outputPath = Join-Path $directory "$($file.BaseName).mp3"

        Invoke-FFmpeg `
            -InputFile $file `
            -OutputPath $outputPath `
            -Arguments @(
            '-vn',
            '-c:a', 'libmp3lame',
            '-q:a', $Quality
        ) `
            -Force:$Force
    }
}


function ConvertTo-WAV {
    [CmdletBinding()]
    param (
        [Parameter(
            Mandatory,
            Position = 0,
            ValueFromPipeline,
            ValueFromPipelineByPropertyName
        )]
        [object] $InputObject,

        [string] $OutputDirectory,

        [switch] $Force
    )

    process {
        $file = Resolve-MediaFile $InputObject

        $directory = if ($OutputDirectory) {
            $OutputDirectory
        }
        else {
            $file.DirectoryName
        }

        $outputPath = Join-Path $directory "$($file.BaseName).wav"

        Invoke-FFmpeg `
            -InputFile $file `
            -OutputPath $outputPath `
            -Arguments @(
            '-vn',
            '-c:a', 'pcm_s16le'
        ) `
            -Force:$Force
    }
}


function ConvertTo-VideoPart {
    [CmdletBinding()]
    param (
        [Parameter(
            Mandatory,
            Position = 0,
            ValueFromPipeline,
            ValueFromPipelineByPropertyName
        )]
        [object] $InputObject,

        [Parameter(Mandatory)]
        [ValidateRange(2, 1000)]
        [int] $NumberOfParts,

        [string] $OutputDirectory,

        [ValidateRange(0, 51)]
        [int] $CRF = 18,

        [ValidateSet(
            'ultrafast',
            'superfast',
            'veryfast',
            'faster',
            'fast',
            'medium',
            'slow',
            'slower',
            'veryslow'
        )]
        [string] $Preset = 'medium',

        [string] $AudioBitrate = '192k',

        [switch] $Force
    )

    process {
        $file = Resolve-MediaFile $InputObject
        $duration = Get-MediaDuration $file

        $partDuration = $duration / $NumberOfParts

        $directory = if ($OutputDirectory) {
            $OutputDirectory
        }
        else {
            $file.DirectoryName
        }

        if (-not (Test-Path -LiteralPath $directory)) {
            New-Item `
                -ItemType Directory `
                -Path $directory `
                -Force |
            Out-Null
        }

        for ($part = 0; $part -lt $NumberOfParts; $part++) {
            $partNumber = $part + 1
            $startTime = $part * $partDuration

            # Make the final part extend exactly to the end of the source.
            $currentDuration = if ($part -eq ($NumberOfParts - 1)) {
                $duration - $startTime
            }
            else {
                $partDuration
            }

            $startText = $startTime.ToString(
                '0.###',
                [Globalization.CultureInfo]::InvariantCulture
            )

            $durationText = $currentDuration.ToString(
                '0.###',
                [Globalization.CultureInfo]::InvariantCulture
            )

            $outputName = '{0}-part-{1:D3}{2}' -f `
                $file.BaseName,
            $partNumber,
            $file.Extension

            $outputPath = Join-Path $directory $outputName

            if ((Test-Path -LiteralPath $outputPath) -and -not $Force) {
                Write-Warning "Skipping existing file: $outputPath"
                continue
            }

            Invoke-FFmpeg `
                -InputFile $file `
                -OutputPath $outputPath `
                -Arguments @(
                '-ss', $startText,
                '-t', $durationText,
                '-map', '0',
                '-c:v', 'libx264',
                '-preset', $Preset,
                '-crf', $CRF,
                '-c:a', 'aac',
                '-b:a', $AudioBitrate,
                '-avoid_negative_ts', 'make_zero'
            ) `
                -Force:$Force
        }
    }
}

function Convert-M4sToMp4Batch {
    [CmdletBinding()]
    param(
        [Parameter(Position = 0)]
        [string]$Path = (Get-Location).Path,

        [switch]$Recurse,

        [switch]$Force
    )

    # Resolve directory
    try {
        $resolvedPath = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    }
    catch {
        throw "Directory not found: $Path"
    }

    if (-not (Test-Path -LiteralPath $resolvedPath -PathType Container)) {
        throw "'$resolvedPath' is not a directory."
    }

    # Build Get-ChildItem parameters
    $gciParams = @{
        LiteralPath = $resolvedPath
        File        = $true
        Filter      = '*.m4s'
    }

    if ($Recurse) {
        $gciParams.Recurse = $true
    }

    $files = Get-ChildItem @gciParams

    if ($files.Count -eq 0) {
        Write-Host "No .m4s files found in '$resolvedPath'."
        return
    }

    Write-Host "Found $($files.Count) .m4s file(s). Converting..."

    $converted = @()
    $warnings = @()

    foreach ($file in $files) {
        try {
            $outputPath = Join-Path $file.DirectoryName "$($file.BaseName).mp4"

            Write-Host "Converting: $($file.Name) → $(Split-Path $outputPath -Leaf)"

            $result = Invoke-FFmpeg `
                -InputFile $file `
                -OutputPath $outputPath `
                -Arguments @(
                '-c:v', 'copy',
                '-c:a', 'copy'
            ) `
                -Force:$Force

            # Ensure output file exists before adding it
            if (Test-Path -LiteralPath $outputPath) {
                $converted += $result
            }
            else {
                $warnings += "Output file missing after conversion: '$outputPath'"
            }
        }
        catch {
            $warnings += "Failed to convert '$($file.FullName)': $_"
        }
    }

    Write-Host ""
    Write-Host "Conversion complete: $($converted.Count) file(s) successfully converted."

    # Ask for deletion
    $answer = Read-Host "Delete original .m4s files? [Y/n]"

    if ($answer -eq '' -or $answer -match '^(y|yes)$') {
        foreach ($file in $files) {
            try {
                Remove-Item -LiteralPath $file.FullName -Force
                Write-Host "Deleted: $($file.Name)"
            }
            catch {
                $warnings += "Could not delete '$($file.FullName)': $_"
            }
        }
    }
    else {
        Write-Host "Original files kept."
    }

    # Print warnings at the end
    if ($warnings.Count -gt 0) {
        Write-Host ""
        Write-Host "⚠ Warnings:" -ForegroundColor Yellow
        foreach ($w in $warnings) {
            Write-Host " - $w" -ForegroundColor Yellow
        }
    }
    else {
        Write-Host ""
        Write-Host "No warnings."
    }
}




function Convert-MP4ToGIFParts {
    [CmdletBinding()]
    param (
        [Parameter(
            Mandatory,
            Position = 0,
            ValueFromPipeline,
            ValueFromPipelineByPropertyName
        )]
        [object] $InputObject,

        [ValidateRange(1, 60)]
        [int] $MaxPartLengthSeconds = 15,

        [ValidateRange(1, 60)]
        [int] $FPS = 24,

        [int]$MaxColors = 120,
        [int]$ForceWidth,

        [switch] $Force
    )

    process {
        $file = Resolve-MediaFile $InputObject

        if ($file.Extension -ne '.mp4') {
            throw "Input must be an MP4 file."
        }

        # Create directory
        $targetDir = Join-Path $file.DirectoryName $file.BaseName
        if (-not (Test-Path -LiteralPath $targetDir)) {
            New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
        }

        # Move MP4 inside directory
        $newPath = Join-Path $targetDir $file.Name
        if (-not (Test-Path -LiteralPath $newPath) -or $Force) {
            Move-Item -LiteralPath $file.FullName -Destination $newPath -Force
        }

        $file = Get-Item -LiteralPath $newPath

        # Get media info
        $info = Get-MediaInfo -Path $file.FullName
        $video = $info.Video | Select-Object -First 1

        #
        # --- Equal-part segmentation using milliseconds ---
        #
        $durationMs = $info.Format.Duration.TotalMilliseconds
        $maxPartMs = $MaxPartLengthSeconds * 1000

        # Number of parts (each must be <= maxPartMs)
        $numberOfParts = [math]::Ceiling($durationMs / $maxPartMs)

        # Equal part duration (always <= maxPartMs)
        $partDurationMs = [math]::Floor($durationMs / $numberOfParts)

        #
        # --- GIF dimensions ---
        #
        
        if ($null -ne $ForceWidth -and $ForceWidth -ne 0) {
            $gifWidth = $ForceWidth
        }
        else {
            $gifWidth = if ($video.Width -ge $video.Height) { 480 } else { 270 }
        }
        $gifHeight = [math]::Round($gifWidth * $video.Height / $video.Width)

        #
        # --- FPS rule ---
        #
        $sourceFPS = [math]::Floor($video.FrameRate)
        if ($sourceFPS -lt 1) { $sourceFPS = 1 }
        $gifFPS = [math]::Min($FPS, $sourceFPS)


        #
        # --- Generate GIF segments directly from original MP4 ---
        #
        for ($i = 0; $i -lt $numberOfParts; $i++) {

            $startMs = $i * $partDurationMs

            # Last part extends exactly to the end
            $lengthMs = if ($i -eq $numberOfParts - 1) {
                $durationMs - $startMs
            }
            else {
                $partDurationMs
            }

            $startSeconds = $startMs / 1000
            $lengthSeconds = $lengthMs / 1000
            #
            # --- Naming format ---
            #
            $outputName = '{0}-part-{1:D3}_{2}x{3}_{4}fps_{5}colors.gif' -f `
                $file.BaseName,
            ($i + 1),
            $gifWidth,
            $gifHeight,
            $gifFPS,
            $MaxColors

            $outputPath = Join-Path $targetDir $outputName

            ConvertTo-GIFSegment `
                -InputFile $file `
                -OutputPath $outputPath `
                -StartSeconds $startSeconds `
                -DurationSeconds $lengthSeconds `
                -Width $gifWidth `
                -FPS $gifFPS `
                -MaxColors $MaxColors `
                -Force:$Force
        }

        Get-Item -LiteralPath $targetDir
    }
}

function Export-Frame {
    [CmdletBinding()]
    param (
        [Parameter(
            Mandatory,
            Position = 0,
            ValueFromPipeline,
            ValueFromPipelineByPropertyName
        )]
        [object] $InputObject,

        [string] $OutputDirectory,

        [int] $Seconds,

        [switch] $Force
    )

    process {
        [System.IO.FileInfo] $file = Resolve-MediaFile $InputObject

        [string] $directory = if ($OutputDirectory) {
            $OutputDirectory
        }
        else {
            $file.DirectoryName
        }

        [string] $outputPath = Join-Path $directory "$($file.BaseName).png"

        $ffmpegArgs = @(
            "-hide_banner",
            "-loglevel", "error",
            '-update', '1',
            '-frames:v', '1',
            '-c:v', 'png'
        )
        if ($Seconds -ne 0){
            if ($Seconds -ge 60){
                $mins = [System.Math]::Floor($Seconds/60)
                $secs = $Seconds - $mins * 60
                $ffmpegArgs += @("-ss","00:${mins}:${secs}")
            }else{
                $ffmpegArgs += @("-ss","00:00:$Seconds")
            }
        }

        Invoke-FFmpeg `
            -InputFile $file `
            -OutputPath $outputPath `
            -Arguments $ffmpegArgs `
            -Force:$Force

            
        <#
            & ffmpeg @(
                "-nostdin",
                "-y",
                "-i",
                $source,
                "-frames:v", "1",
                "-f", "image2",
                $destination
            )
        #>
    }
}

function Invoke-MediaTagger {
    [CmdletBinding()]
    param (
        [Parameter()]
        [string]$Directory = (Get-Location).Path
    )

    $ErrorActionPreference = "Stop"

    $tagsFile = Join-Path $Directory "tags.json"
    $sortedDirectory = Join-Path $Directory "sorted"

    # Create a sample tags.json and exit if it does not exist
    if (-not (Test-Path -LiteralPath $tagsFile)) {
        $sample = [ordered]@{
            availableTags = @(
                "family",
                "friends",
                "travel",
                "work",
                "favorite"
            )
        }

        $sample |
        ConvertTo-Json -Depth 10 |
        Set-Content -LiteralPath $tagsFile -Encoding UTF8

        Write-Host "Created $tagsFile."
        Write-Host "Edit the availableTags list, then run the function again."
        return
    }

    if (-not (Get-Command mpv -ErrorAction SilentlyContinue)) {
        throw "mpv is not installed. Install it with: sudo apt install mpv"
    }

    if (-not (Get-Command getfattr -ErrorAction SilentlyContinue)) {
        throw "getfattr is not installed. Install it with: sudo apt install attr"
    }

    if (-not (Get-Command setfattr -ErrorAction SilentlyContinue)) {
        throw "setfattr is not installed. Install it with: sudo apt install attr"
    }

    if (-not (Get-Command fzf -ErrorAction SilentlyContinue)) {
        throw "fzf is not installed. Install it with: sudo apt install fzf"
    }

    # Load the available tag names from tags.json
    $tagConfig = Get-Content -LiteralPath $tagsFile -Raw |
    ConvertFrom-Json

    $availableTags = @($tagConfig.availableTags)

    if ($availableTags.Count -eq 0) {
        throw "No tags were found in the availableTags array in $tagsFile."
    }

    if (-not (Test-Path -LiteralPath $sortedDirectory)) {
        New-Item -ItemType Directory -Path $sortedDirectory | Out-Null
    }

    $extensions = @(
        ".gif",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".mp4"
    )

    $mediaFiles = @(
        Get-ChildItem -LiteralPath $Directory -File |
        Where-Object {
            $extensions -contains $_.Extension.ToLowerInvariant()
        } |
        Sort-Object Name
    )

    if ($mediaFiles.Count -eq 0) {
        Write-Host "No supported media files found."
        return
    }

    foreach ($file in $mediaFiles) {
        Clear-Host

        # Read current tags from Dolphin's extended attribute
        $tagOutput = & getfattr `
            --only-values `
            --name user.xdg.tags `
            -- $file.FullName 2>$null

        if ($LASTEXITCODE -eq 0 -and $null -ne $tagOutput) {
            $tagText = ($tagOutput -join "").Trim()

            if ($tagText.Length -gt 0) {
                $currentTags = @(
                    $tagText -split "," |
                    ForEach-Object { $_.Trim() } |
                    Where-Object { $_ -ne "" }
                )
            }
            else {
                $currentTags = @()
            }
        }
        else {
            $currentTags = @()
        }

        Write-Host "File: $($file.Name)"
        Write-Host ""

        if ($currentTags.Count -gt 0) {
            Write-Host "Current tags: $($currentTags -join ', ')"
        }
        else {
            Write-Host "Current tags: none"
        }

        Write-Host ""
        Write-Host "Opening media in mpv..."
        Write-Host ""

        $mpvProcess = Start-Process `
            -FilePath "mpv" `
            -ArgumentList @(
            "--force-window=yes",
            "--keep-open=yes",
            "--really-quiet",
            "--no-terminal",
            #"--pause",
            "--loop",
            "--",
            $file.FullName
        ) `
            -PassThru

        Start-Sleep -Milliseconds 300

        #
        # --- FZF TAG SELECTION ---
        #

        # Run fzf in multi-select mode
        $selection = $availableTags |
        fzf --multi `
            --reverse `
            --prompt="Select tags: " `
            --header="TAB = toggle, ENTER = confirm, s = skip, q = quit" `
            --expect=q, s

        # Close mpv
        if (-not $mpvProcess.HasExited) {
            Stop-Process -Id $mpvProcess.Id -Force -ErrorAction SilentlyContinue
        }

        # If fzf aborted (s, q, ESC)
        if ($LASTEXITCODE -ne 0) {

            Write-Host "Exiting."
            return
        }

        # Convert fzf output (plain tag names) into an array

        $lines = $selection -split "`n"

        $key = $lines[0].Trim()

        # Handle q and s
        if ($key -eq "q") {
            Write-Host "Exiting."
            return
        }

        if ($key -eq "s") {
            Write-Host "Skipped $($file.Name)."
            Start-Sleep -Milliseconds 500
            continue
        }

        $newTags = @(
            $lines | ForEach-Object { $_.Trim() }
        )

        $currentTags = @($newTags | Sort-Object -Unique)

        #
        # --- WRITE TAGS ---
        #

        if ($currentTags.Count -eq 0) {
            & setfattr `
                --remove user.xdg.tags `
                -- $file.FullName 2>$null
        }
        else {
            $tagValue = $currentTags -join ","

            & setfattr `
                --name user.xdg.tags `
                --value $tagValue `
                -- $file.FullName
        }

        if ($LASTEXITCODE -ne 0) {
            Write-Host "Could not set tags on $($file.Name)."
            Start-Sleep -Seconds 1
            continue
        }

        #
        # --- MOVE FILE ---
        #

        $destination = Join-Path $sortedDirectory $file.Name

        if (Test-Path -LiteralPath $destination) {
            $baseName = [System.IO.Path]::GetFileNameWithoutExtension($file.Name)
            $extension = [System.IO.Path]::GetExtension($file.Name)
            $counter = 1

            do {
                $newName = "{0}_{1}{2}" -f $baseName, $counter, $extension
                $destination = Join-Path $sortedDirectory $newName
                $counter++
            } while (Test-Path -LiteralPath $destination)
        }

        Move-Item `
            -LiteralPath $file.FullName `
            -Destination $destination

        Write-Host ""
        Write-Host "Tags saved: $($currentTags -join ', ')"
        Write-Host "Moved to: $destination"

        Start-Sleep -Milliseconds 700
    }

    Write-Host ""
    Write-Host "Finished processing all media files."
}

function Find-DuplicateMedia {
    [CmdletBinding()]
    param(
        [Parameter(Position = 0)]
        [string]$Path = (Get-Location),

        [switch]$Recurse,
        [switch]$Display,
        [switch]$DeleteMode,
        [switch]$PassThru
    )

    # Media extensions to scan
    $extensions = '*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp', '*.mp4', '*.avi', '*.mov', '*.mkv', '*.webm'

    # Build Get-ChildItem parameters

    if ($Recurse) { 
        $gciParams = @{
            Path    = $Path
            File    = $true
            Include = $extensions
            Recurse = $true
        }
    }
    else { 
        $gciParams = @{
            Path    = $extensions | ForEach-Object { Join-Path -Path $Path -ChildPath $_ }
            File    = $true
            Recurse = $false
        }
    }

    # Collect files
    $files = Get-ChildItem @gciParams

    Write-Host "Found $($files.Length) files."

    # Compute hashes + XDG tags
    $hashed = $files | ForEach-Object {
        $h = Get-FileHash $_.FullName -Algorithm SHA256

        # Read XDG tags (Linux extended attributes)
        $tags = ""
        try {
            $tags = (getfattr -n user.xdg.tags --only-values $_.FullName 2>$null)
        }
        catch {}

        [PSCustomObject]@{
            Name = $_.Name
            Path = $_.FullName
            Size = $_.Length
            Hash = $h.Hash
            Tags = $tags
        }
    }

    # Group by hash → duplicates
    $dupes = $hashed | Group-Object Hash | Where-Object { $_.Count -gt 1 }

    if ($Display) {
        foreach ($group in $dupes) {
            Write-Host ""
            Write-Host "Duplicate Set (Hash: $($group.Name))" -ForegroundColor Cyan
            $group.Group | Select-Object Name, Size, Tags, Path | Format-Table
        }
    }

    if ($DeleteMode) {
        foreach ($group in $dupes) {
            Write-Host ""
            Write-Host "Duplicate Set (Hash: $($group.Name))" -ForegroundColor Yellow
            $items = $group.Group

            # Display choices
            $i = 1
            foreach ($item in $items) {
                Write-Host "[$i] $($item.Name)  ($([math]::Round($item.Size/1KB,2)) KB)"
                Write-Host "     Path: $($item.Path)"
                Write-Host "     Tags: $($item.Tags)"
                $i++
            }

            # Ask user which one to keep
            $choice = Read-Host "Select the number of the file you want to KEEP"
            if ($choice -notmatch '^\d+$' -or $choice -lt 1 -or $choice -gt $items.Count) {
                Write-Host "Invalid selection. Skipping this group." -ForegroundColor Red
                continue
            }

            $keep = $items[$choice - 1]

            # Delete the rest
            foreach ($item in $items) {
                if ($item.Path -ne $keep.Path) {
                    Write-Host "Deleting: $($item.Path)" -ForegroundColor Red
                    Remove-Item $item.Path -Force
                }
            }

            Write-Host "Kept: $($keep.Path)" -ForegroundColor Green
        }
    }

    if ($PassThru) {
        return $dupes
    }
}


function Find-DuplicateMediaHybrid {
    [CmdletBinding()]
    param(
        [Parameter(Position = 0)]
        [string]$Path = (Get-Location),

        [switch]$Recurse,
        [switch]$Display,
        [switch]$DeleteMode,
        [switch]$PassThru,

        [int]$ImageThreshold = 10,
        [int]$VideoThreshold = 15,
        [int]$VideoFrameRate = 1,
        [int]$VideoFrameLimit = 12,

        [string]$CacheFile = (Join-Path $env:HOME ".cache_find_duplicate_media.json"),
        [string]$phashCmd = "compute-phash",   # command that prints hex pHash for an image
        [string]$ffmpegCmd = "ffmpeg",
        [string]$ffprobeCmd = "ffprobe"
    )

    # --- helpers: cache load/save ---
    $cache = @{}
    if (Test-Path $CacheFile) {
        try { 
            $content = Get-Content $CacheFile -Raw
            if ($content.Trim() ) {
                $cache = $content | ConvertFrom-Json -ErrorAction Stop 
            }
        }
        catch { $cache = @{} }
    }
    else {
        # ensure directory exists
        $dir = Split-Path $CacheFile -Parent
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    }

    function Save-Cache {
        try {
            $cache | ConvertTo-Json -Depth 5 | Set-Content -Path $CacheFile -Force
        }
        catch { }
    }

    # --- helpers: hashing & phash ---
    function Get-SHA256($path) {
        try {
            (Get-FileHash -Algorithm SHA256 -Path $path -ErrorAction Stop).Hash
        }
        catch { $null }
    }

    function Get-ImagePHashCached($path) {
        $info = Get-Item $path
        $key = "$($info.FullName)|$($info.LastWriteTimeUtc.Ticks)|sha"
        if ($cache."$key" -and $cache."$key".phash) { return $cache."$key".phash }

        if (-not (Get-Command $phashCmd -ErrorAction SilentlyContinue)) {
            Write-Host "pHash command '$phashCmd' not found in PATH." -ForegroundColor Red
            return $null
        }
        $out = & $phashCmd $path 2>&1
        if ($LASTEXITCODE -ne 0) {
            return $null
        }
        $ph = $out.Trim()
        $cache | Add-Member -MemberType NoteProperty -Name $key -Value @{ phash = $ph; type = "image"; mtime = $info.LastWriteTimeUtc.Ticks }
        Save-Cache
        return $ph
    }

    function Get-VideoFramePHashesCached($path, $frameRate, $frameLimit) {
        $info = Get-Item $path
        $key = "$($info.FullName)|$($info.LastWriteTimeUtc.Ticks)|frames"
        if ($cache."$key" -and $cache."$key".frames) { return , $cache."$key".frames }

        # extract frames to temp dir
        $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("frames_{0}_{1}" -f ([System.Guid]::NewGuid().ToString("N")), (Get-Random))
        New-Item -ItemType Directory -Path $tmp | Out-Null

        $ffmpegArgs = @("-hide_banner", "-loglevel", "error", "-i", $path, "-vf", "fps=$frameRate", "-q:v", "2", (Join-Path $tmp "frame_%04d.jpg"))
        & $ffmpegCmd @ffmpegArgs

        $frames = Get-ChildItem -Path $tmp -Filter 'frame_*.jpg' -ErrorAction SilentlyContinue | Sort-Object Name
        if ($frames.Count -gt $frameLimit) {
            $step = [math]::Max(1, [math]::Floor($frames.Count / $frameLimit))
            $frames = $frames | Where-Object { ($frames.IndexOf($_) % $step) -eq 0 } | Select-Object -First $frameLimit
        }

        $phashes = @()
        $fi = 0
        foreach ($fr in $frames) {
            $fi++
            Write-Progress -Activity "Hashing video frames" -Status "Hashing frames for $([System.IO.Path]::GetFileName($path)) - frame $fi/$($frames.Count)" -PercentComplete ([int](($fi / $frames.Count) * 100))
            $ph = Get-ImagePHashCached $fr.FullName
            if ($ph) { $phashes += $ph }
        }

        # cleanup
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue

        $cache | Add-Member -MemberType NoteProperty -Name $key -Value @{ frames = $phashes; type = "video"; mtime = $info.LastWriteTimeUtc.Ticks }
        Save-Cache
        return , $phashes
    }

    # --- helper: detect animated gif (use ffprobe if available) ---
    function Test-IsAnimatedGif($path) {
        try {
            if (-not (Get-Command $ffprobeCmd -ErrorAction SilentlyContinue)) {
                # fallback: treat all .gif as animated (safer)
                return $true
            }
            $ffprobeargs = @("-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames", "-of", "default=nokey=1:noprint_wrappers=1", $path)
            $out = & $ffprobeCmd @ffprobeargs 2>$null
            if ($out) {
                $n = $out.Trim()
                if ($n -match '^\d+$') { return ([int]$n -gt 1) }
            }
            # if nb_frames not available, try counting packets (slower)
            $ffprobeargs2 = @("-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries", "stream=nb_read_packets", "-of", "default=nokey=1:noprint_wrappers=1", $path)
            $out2 = & $ffprobeCmd @ffprobeargs2 2>$null
            if ($out2 -and $out2.Trim() -match '^\d+$') { return ([int]$out2.Trim() -gt 1) }
            # fallback: assume animated
            return $true
        }
        catch { return $true }
    }

    # --- helper: hex hamming distance ---
    function HammingDistanceHex($h1, $h2) {
        if (-not $h1 -or -not $h2) { return [int]::MaxValue }
        if ($h1.Length -lt $h2.Length) { $h1 = $h1.PadLeft($h2.Length, '0') }
        if ($h2.Length -lt $h1.Length) { $h2 = $h2.PadLeft($h1.Length, '0') }
        $count = 0
        for ($i = 0; $i -lt $h1.Length; $i += 2) {
            $b1 = [Convert]::ToInt32($h1.Substring($i, 2), 16)
            $b2 = [Convert]::ToInt32($h2.Substring($i, 2), 16)
            $x = $b1 -bxor $b2
            while ($x -ne 0) {
                $count += $x -band 1
                $x = $x -shr 1
            }
        }
        return $count
    }

    # --- collect files ---
    $imageExt = '*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp', '*.webp', '*.tiff'
    $videoExt = '*.mp4', '*.mkv', '*.mov', '*.avi', '*.webm', '*.flv'

    $gciParams = @{ Path = $Path; File = $true; Include = $imageExt + $videoExt }
    if ($Recurse) { $gciParams.Recurse = $true }
    $files = Get-ChildItem @gciParams -ErrorAction SilentlyContinue

    if (-not $files -or $files.Count -eq 0) {
        Write-Host "No media files found." -ForegroundColor Yellow
        return
    }

    # --- scan & fingerprint with progress ---
    $total = $files.Count
    $index = 0
    $items = @()

    foreach ($f in $files) {
        $index++
        $percent = [int](($index / $total) * 100)
        Write-Progress -Activity "Scanning media files" -Status "Processing $index of $total : $($f.Name)" -PercentComplete $percent

        $ext = $f.Extension.ToLower()
        $isGif = ($ext -eq '.gif')
        $isImage = -not $isGif -and ($imageExt -contains ("*" + $ext))
        $isVideo = $isGif -or ($videoExt -contains ("*" + $ext))

        # if gif, detect if animated; if single-frame gif treat as image
        if ($isGif) {
            $animated = Test-IsAnimatedGif $f.FullName
            if (-not $animated) { $isImage = $true; $isVideo = $false }
        }

        $obj = [PSCustomObject]@{
            Name         = $f.Name
            Path         = $f.FullName
            Size         = $f.Length
            SHA256       = $null
            Type         = if ($isVideo) { 'Video' } elseif ($isImage) { 'Image' } else { 'Other' }
            PHash        = $null
            FramePHashes = @()
            Tags         = ""
        }

        # SHA256
        Write-Progress -Activity "Scanning media files" -Status "Hashing (SHA256): $($f.Name)" -PercentComplete $percent
        $obj.SHA256 = Get-SHA256 $f.FullName

        # XDG tags
        try { $obj.Tags = (getfattr -n user.xdg.tags --only-values $f.FullName 2>$null) } catch {}

        if ($obj.Type -eq 'Image') {
            Write-Progress -Activity "Scanning media files" -Status "Computing pHash for image: $($f.Name)" -PercentComplete $percent
            $obj.PHash = Get-ImagePHashCached $f.FullName
        }
        elseif ($obj.Type -eq 'Video') {
            Write-Progress -Activity "Scanning media files" -Status "Extracting frames: $($f.Name)" -PercentComplete $percent
            $frames = Get-VideoFramePHashesCached -path $f.FullName -frameRate $VideoFrameRate -frameLimit $VideoFrameLimit
            if ($frames) { $obj.FramePHashes = $frames }
        }

        $items += $obj
    }

    Write-Progress -Activity "Scanning media files" -Completed

    # --- all-vs-all comparisons with union-find grouping ---
    $all = $items
    $parent = @{}
    function Find($x) {
        if (-not $parent.ContainsKey($x)) { $parent[$x] = $x }
        while ($parent[$x] -ne $x) { $x = $parent[$x] }
        return $x
    }
    function Union($a, $b) {
        $ra = Find $a; $rb = Find $b
        if ($ra -ne $rb) { $parent[$rb] = $ra }
    }

    $n = $all.Count
    for ($i = 0; $i -lt $n; $i++) {
        for ($j = $i + 1; $j -lt $n; $j++) {
            $a = $all[$i]; $b = $all[$j]

            # exact duplicate quick path
            if ($a.SHA256 -and $b.SHA256 -and $a.SHA256 -eq $b.SHA256) {
                Union $a.Path $b.Path
                continue
            }

            # image-image
            if ($a.Type -eq 'Image' -and $b.Type -eq 'Image' -and $a.PHash -and $b.PHash) {
                $d = HammingDistanceHex $a.PHash $b.PHash
                if ($d -le $ImageThreshold) { Union $a.Path $b.Path }
                continue
            }

            # image-video
            if ($a.Type -eq 'Image' -and $b.Type -eq 'Video' -and $a.PHash -and $b.FramePHashes.Count -gt 0) {
                $min = [int]::MaxValue
                foreach ($fh in $b.FramePHashes) {
                    $d = HammingDistanceHex $a.PHash $fh
                    if ($d -lt $min) { $min = $d }
                    if ($min -le $VideoThreshold) { break }
                }
                if ($min -le $VideoThreshold) { Union $a.Path $b.Path }
                continue
            }
            if ($a.Type -eq 'Video' -and $b.Type -eq 'Image' -and $b.PHash -and $a.FramePHashes.Count -gt 0) {
                $min = [int]::MaxValue
                foreach ($fh in $a.FramePHashes) {
                    $d = HammingDistanceHex $b.PHash $fh
                    if ($d -lt $min) { $min = $d }
                    if ($min -le $VideoThreshold) { break }
                }
                if ($min -le $VideoThreshold) { Union $a.Path $b.Path }
                continue
            }

            # video-video
            if ($a.Type -eq 'Video' -and $b.Type -eq 'Video' -and $a.FramePHashes.Count -gt 0 -and $b.FramePHashes.Count -gt 0) {
                $min = [int]::MaxValue
                foreach ($h1 in $a.FramePHashes) {
                    foreach ($h2 in $b.FramePHashes) {
                        $d = HammingDistanceHex $h1 $h2
                        if ($d -lt $min) { $min = $d }
                        if ($min -le $VideoThreshold) { break }
                    }
                    if ($min -le $VideoThreshold) { break }
                }
                if ($min -le $VideoThreshold) { Union $a.Path $b.Path }
                continue
            }
        }
    }

    # collect groups
    $groups = @{}
    foreach ($it in $items) {
        $root = Find $it.Path
        if (-not $groups.ContainsKey($root)) { $groups[$root] = @() }
        $groups[$root] += $it
    }

    $allGroups = $groups.GetEnumerator() | Where-Object { $_.Value.Count -gt 1 } | ForEach-Object { , $_.Value }
    

    # --- display / delete UI ---
    if ($Display) {
        Write-Host "`nDuplicate sets (all-vs-all):" -ForegroundColor Cyan
        foreach ($g in $allGroups) {
            Write-Host "`n--- Duplicate Set ---" -ForegroundColor Yellow
            foreach ($it in $g) {
                $meta = if ($it.Type -eq 'Image') { "pHash:$($it.PHash)" } elseif ($it.Type -eq 'Video') { "Frames:$($it.FramePHashes.Count)" } else { "" }
                Write-Host (" - {0}  ({1} KB)  {2}" -f $it.Name, [math]::Round($it.Size / 1KB, 2), $meta)
                Write-Host "     Path: $($it.Path)"
                Write-Host "     Tags: $($it.Tags)"
            }
        }
    }

    if ($DeleteMode) {
        foreach ($g in $allGroups) {
            Write-Host "`nDuplicate Set" -ForegroundColor Yellow
            $itemsList = $g
            $i = 1
            foreach ($it in $itemsList) {
                $meta = if ($it.Type -eq 'Image') { "pHash:$($it.PHash)" } elseif ($it.Type -eq 'Video') { "Frames:$($it.FramePHashes.Count)" } else { "" }
                Write-Host "[$i] $($it.Name)  ($([math]::Round($it.Size/1KB,2)) KB)  $meta"
                Write-Host "     Path: $($it.Path)"
                Write-Host "     Tags: $($it.Tags)"
                $i++
            }
            $choice = Read-Host "Select the number of the file you want to KEEP"
            if ($choice -notmatch '^\d+$' -or $choice -lt 1 -or $choice -gt $itemsList.Count) {
                Write-Host "Invalid selection. Skipping." -ForegroundColor Red
                continue
            }
            $keep = $itemsList[$choice - 1]
            foreach ($it in $itemsList) {
                if ($it.Path -ne $keep.Path) {
                    Write-Host "Deleting: $($it.Path)" -ForegroundColor Red
                    Remove-Item $it.Path -Force
                }
            }
            Write-Host "Kept: $($keep.Path)" -ForegroundColor Green
        }
    }

    if ($PassThru) {
        return [PSCustomObject]@{
            Groups    = $allGroups
            Items     = $items
            CacheFile = $CacheFile
        }
    }
}



Export-ModuleMember -Function "Repair-MediaFileExtensions", "Get-MediaInfo", "Resolve-MediaFile", "Get-MediaDuration", "Invoke-FFmpeg", "Get-VideoDimensions", "ConvertTo-GIF", "ConvertTo-MP4", "ConvertTo-PNG", "ConvertTo-JPG", "ConvertTo-WEBP", "ConvertTo-MP3", "ConvertTo-WAV", "ConvertTo-VideoPart", "Invoke-MediaTagger", "Find-DuplicateMedia", "Find-DuplicateMediaHybrid", "Convert-MP4ToGIFParts", "ConvertTo-GIFSegment", "Convert-M4sToMp4Batch", "Merge-VideoAudio", "Export-Frame"