[CmdletBinding()]
param(
    [string]$BrandManifestPath,
    [string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not $BrandManifestPath) {
    $BrandManifestPath = Join-Path $repoRoot 'packaging\windows-client-v2\branding\brand-assets.json'
}
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $repoRoot 'dist\windows-client-v2\.brand-preview'
}
$BrandManifestPath = [System.IO.Path]::GetFullPath($BrandManifestPath)
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
$brandDirectory = Split-Path $BrandManifestPath -Parent
$brand = Get-Content -LiteralPath $BrandManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$sourcePath = Join-Path $brandDirectory ([string]$brand.source_file)
if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
    throw "Brand source asset is missing: $sourcePath"
}
$sourceHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($sourceHash -ne ([string]$brand.source_sha256).ToLowerInvariant()) {
    throw "Brand source hash mismatch. Expected $($brand.source_sha256), got $sourceHash"
}

Add-Type -AssemblyName System.Drawing
$source = [System.Drawing.Image]::FromFile($sourcePath)
try {
    if ($source.Width -ne [int]$brand.source_width -or $source.Height -ne [int]$brand.source_height) {
        throw "Brand source dimensions must be $($brand.source_width)x$($brand.source_height)."
    }
    if ($source.Width -ne $source.Height) { throw 'Brand source must be square.' }

    if (Test-Path -LiteralPath $OutputDirectory) {
        Remove-Item -LiteralPath $OutputDirectory -Recurse -Force
    }
    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

    function New-BrandBitmap {
        param(
            [Parameter(Mandatory = $true)][System.Drawing.Image]$Source,
            [Parameter(Mandatory = $true)][int]$Size,
            [string]$StatusColor
        )

        $bitmap = [System.Drawing.Bitmap]::new(
            $Size,
            $Size,
            [System.Drawing.Imaging.PixelFormat]::Format32bppArgb
        )
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphics.Clear([System.Drawing.Color]::Transparent)
            $graphics.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceOver
            $graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
            $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
            $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

            $clip = [System.Drawing.Drawing2D.GraphicsPath]::new()
            try {
                $clip.AddEllipse(1, 1, [Math]::Max(1, $Size - 2), [Math]::Max(1, $Size - 2))
                $graphics.SetClip($clip)
                $inset = [int][Math]::Round($Source.Width * [double]$brand.crop_inset_ratio)
                $sourceRect = [System.Drawing.Rectangle]::new(
                    $inset,
                    $inset,
                    $Source.Width - (2 * $inset),
                    $Source.Height - (2 * $inset)
                )
                $targetRect = [System.Drawing.Rectangle]::new(0, 0, $Size, $Size)
                $graphics.DrawImage(
                    $Source,
                    $targetRect,
                    $sourceRect,
                    [System.Drawing.GraphicsUnit]::Pixel
                )
                $graphics.ResetClip()
            }
            finally {
                $clip.Dispose()
            }

            if ($StatusColor) {
                $diameter = [Math]::Max(5, [int][Math]::Round($Size * 0.34))
                $borderWidth = [Math]::Max(1, [single]($Size * 0.055))
                $margin = [Math]::Max(1, [int][Math]::Round($Size * 0.025))
                $x = $Size - $diameter - $margin
                $y = $Size - $diameter - $margin
                $border = [System.Drawing.Pen]::new([System.Drawing.Color]::White, $borderWidth)
                $fill = [System.Drawing.SolidBrush]::new(
                    [System.Drawing.ColorTranslator]::FromHtml($StatusColor)
                )
                try {
                    $graphics.FillEllipse($fill, $x, $y, $diameter, $diameter)
                    $graphics.DrawEllipse($border, $x, $y, $diameter, $diameter)
                }
                finally {
                    $fill.Dispose()
                    $border.Dispose()
                }
            }
        }
        finally {
            $graphics.Dispose()
        }
        return $bitmap
    }

    function ConvertTo-PngBytes {
        param([Parameter(Mandatory = $true)][System.Drawing.Bitmap]$Bitmap)
        $stream = [System.IO.MemoryStream]::new()
        try {
            $Bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
            return $stream.ToArray()
        }
        finally {
            $stream.Dispose()
        }
    }

    function Write-MultiSizeIcon {
        param(
            [Parameter(Mandatory = $true)][string]$Path,
            [Parameter(Mandatory = $true)][object[]]$Frames
        )
        $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Create)
        $writer = [System.IO.BinaryWriter]::new($stream)
        try {
            $writer.Write([uint16]0)
            $writer.Write([uint16]1)
            $writer.Write([uint16]$Frames.Count)
            $offset = 6 + (16 * $Frames.Count)
            foreach ($frame in $Frames) {
                $dimension = [int]$frame.size
                $writer.Write([byte]($(if ($dimension -eq 256) { 0 } else { $dimension })))
                $writer.Write([byte]($(if ($dimension -eq 256) { 0 } else { $dimension })))
                $writer.Write([byte]0)
                $writer.Write([byte]0)
                $writer.Write([uint16]1)
                $writer.Write([uint16]32)
                $writer.Write([uint32]$frame.bytes.Length)
                $writer.Write([uint32]$offset)
                $offset += $frame.bytes.Length
            }
            foreach ($frame in $Frames) { $writer.Write([byte[]]$frame.bytes) }
        }
        finally {
            $writer.Dispose()
            $stream.Dispose()
        }
    }

    $sizes = @($brand.icon_sizes | ForEach-Object { [int]$_ })
    if (($sizes | Sort-Object -Unique).Count -ne $sizes.Count -or $sizes -notcontains 256) {
        throw 'Brand icon sizes must be unique and include 256.'
    }
    $variants = [ordered]@{ base = $null }
    foreach ($property in $brand.tray_status_colors.PSObject.Properties) {
        $variants[$property.Name] = [string]$property.Value
    }
    $outputs = [ordered]@{}
    foreach ($variant in $variants.GetEnumerator()) {
        $frames = @()
        foreach ($size in $sizes) {
            $bitmap = New-BrandBitmap -Source $source -Size $size -StatusColor $variant.Value
            try {
                $frames += [pscustomobject]@{
                    size = $size
                    bytes = ConvertTo-PngBytes -Bitmap $bitmap
                }
            }
            finally {
                $bitmap.Dispose()
            }
        }
        $fileName = if ($variant.Key -eq 'base') {
            'channel-agent.ico'
        } else {
            "channel-agent-tray-$($variant.Key).ico"
        }
        $path = Join-Path $OutputDirectory $fileName
        Write-MultiSizeIcon -Path $path -Frames $frames
        $outputs[$fileName] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    }

    $avatar = New-BrandBitmap -Source $source -Size 1024
    try {
        $avatarPath = Join-Path $OutputDirectory 'channel-agent-avatar.png'
        $avatar.Save($avatarPath, [System.Drawing.Imaging.ImageFormat]::Png)
        $outputs['channel-agent-avatar.png'] = (
            Get-FileHash -LiteralPath $avatarPath -Algorithm SHA256
        ).Hash.ToLowerInvariant()
    }
    finally {
        $avatar.Dispose()
    }

    [ordered]@{
        schema_version = 'channel-agent-brand-build.v1'
        brand_version = [string]$brand.brand_version
        product_version = [string]$brand.product_version
        source_sha256 = $sourceHash
        icon_sizes = $sizes
        outputs = $outputs
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (
        Join-Path $OutputDirectory 'brand-build-manifest.json'
    ) -Encoding UTF8
}
finally {
    $source.Dispose()
}

Write-Output "brand_assets=$OutputDirectory"
