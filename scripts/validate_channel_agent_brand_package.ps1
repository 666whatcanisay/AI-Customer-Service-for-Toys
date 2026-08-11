[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$PackageRoot
)

$ErrorActionPreference = 'Stop'
$PackageRoot = [System.IO.Path]::GetFullPath($PackageRoot)
$manifestPath = Join-Path $PackageRoot 'release-manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw 'Brand Asset Gate requires release-manifest.json.'
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.branding_status -eq 'fallback') {
    foreach ($property in @(
        'executable_icon_sha256',
        'tray_normal_sha256',
        'tray_warning_sha256',
        'tray_error_sha256',
        'tray_offline_sha256',
        'avatar_sha256'
    )) {
        if ($manifest.branding.$property) {
            throw "Fallback branding must not claim an official hash: $property"
        }
    }
    Write-Output 'branding_status=fallback'
    exit 0
}
if ($manifest.branding_status -ne 'official') {
    throw "Unknown branding status: $($manifest.branding_status)"
}

$files = [ordered]@{
    'channel-agent.ico' = 'executable_icon_sha256'
    'channel-agent-tray-normal.ico' = 'tray_normal_sha256'
    'channel-agent-tray-warning.ico' = 'tray_warning_sha256'
    'channel-agent-tray-error.ico' = 'tray_error_sha256'
    'channel-agent-tray-offline.ico' = 'tray_offline_sha256'
    'channel-agent-avatar.png' = 'avatar_sha256'
}
$expectedSizes = @($manifest.branding.icon_sizes | ForEach-Object { [int]$_ })
foreach ($item in $files.GetEnumerator()) {
    $path = Join-Path $PackageRoot "assets\branding\$($item.Key)"
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Official branding asset is missing: $($item.Key)"
    }
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    $expected = ([string]$manifest.branding.($item.Value)).ToLowerInvariant()
    if (-not $expected -or $actual -ne $expected) {
        throw "Official branding hash mismatch: $($item.Key)"
    }
    if ($item.Key.EndsWith('.ico', [System.StringComparison]::OrdinalIgnoreCase)) {
        $bytes = [System.IO.File]::ReadAllBytes($path)
        if ($bytes.Length -lt 6 -or [BitConverter]::ToUInt16($bytes, 2) -ne 1) {
            throw "Invalid ICO header: $($item.Key)"
        }
        $count = [BitConverter]::ToUInt16($bytes, 4)
        $sizes = @()
        for ($index = 0; $index -lt $count; $index++) {
            $offset = 6 + (16 * $index)
            if ($offset + 16 -gt $bytes.Length) { throw "Truncated ICO: $($item.Key)" }
            $sizes += $(if ($bytes[$offset] -eq 0) { 256 } else { [int]$bytes[$offset] })
        }
        if (($sizes -join ',') -ne ($expectedSizes -join ',')) {
            throw "ICO size set mismatch: $($item.Key)"
        }
    }
}

$buildManifestPath = Join-Path $PackageRoot 'assets\branding\brand-build-manifest.json'
$buildManifest = Get-Content -LiteralPath $buildManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (
    $buildManifest.source_sha256 -ne $manifest.branding.source_asset_sha256 -or
    $buildManifest.product_version -ne $manifest.version -or
    $buildManifest.brand_version -ne $manifest.branding.brand_version
) {
    throw 'Brand build metadata does not match the release manifest.'
}
$uiAvatar = Join-Path $PackageRoot 'ui\channel-agent-avatar.png'
$uiIndex = Join-Path $PackageRoot 'ui\index.html'
if ((Test-Path -LiteralPath (Join-Path $PackageRoot 'ui') -PathType Container)) {
    if (-not (Test-Path -LiteralPath $uiAvatar -PathType Leaf)) {
        throw 'Agent UI avatar is missing.'
    }
    if (
        (Get-FileHash -LiteralPath $uiAvatar -Algorithm SHA256).Hash.ToLowerInvariant() -ne
        ([string]$manifest.branding.avatar_sha256).ToLowerInvariant()
    ) {
        throw 'Agent UI avatar hash mismatch.'
    }
    if ((Get-Content -LiteralPath $uiIndex -Raw -Encoding UTF8) -notmatch 'data-channel-agent-brand') {
        throw 'Agent UI favicon marker is missing.'
    }
}

Write-Output 'branding_status=official'
Write-Output "brand_version=$($manifest.branding.brand_version)"
