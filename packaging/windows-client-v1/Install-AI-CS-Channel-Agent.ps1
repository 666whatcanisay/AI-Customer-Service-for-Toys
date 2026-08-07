[CmdletBinding()]
param(
    [string]$PackageRoot,
    [string]$InstallRoot,
    [string]$DataRoot,
    [string]$StartupDirectory,
    [switch]$EnableAutoStart,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
if (-not $PackageRoot) { $PackageRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')) }
$PackageRoot = [System.IO.Path]::GetFullPath($PackageRoot)
if (-not $InstallRoot) { $InstallRoot = Join-Path $env:LOCALAPPDATA 'Programs\AI-CS\ChannelAgent' }
if (-not $DataRoot) { $DataRoot = Join-Path $env:LOCALAPPDATA 'AI-CS\ChannelAgent' }
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
$DataRoot = [System.IO.Path]::GetFullPath($DataRoot)

foreach ($required in @('ChannelAgent.exe', 'app\channel-agent.pyz', 'release-manifest.json')) {
    if (-not (Test-Path -LiteralPath (Join-Path $PackageRoot $required) -PathType Leaf)) {
        throw "Required package file is missing: $required"
    }
}
if ($InstallRoot -eq $PackageRoot) { throw 'InstallRoot cannot equal PackageRoot.' }
if ((Test-Path -LiteralPath $InstallRoot) -and -not $Force) {
    throw 'InstallRoot already exists; use -Force for an approved upgrade.'
}

New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
Get-ChildItem -LiteralPath $PackageRoot -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $InstallRoot -Recurse -Force
}
foreach ($relative in @('config', 'logs', 'runtime')) {
    New-Item -ItemType Directory -Path (Join-Path $DataRoot $relative) -Force | Out-Null
}
$example = Join-Path $InstallRoot 'config\agent.example.json'
$activeConfig = Join-Path $DataRoot 'config\agent.json'
if (-not (Test-Path -LiteralPath $activeConfig)) {
    Copy-Item -LiteralPath $example -Destination $activeConfig
}
$manifest = Get-Content -LiteralPath (Join-Path $InstallRoot 'release-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
[ordered]@{
    schema_version = '1.0'
    installed_version = $manifest.version
    install_root = $InstallRoot
    data_root = $DataRoot
    installed_at = [DateTimeOffset]::UtcNow.ToString('o')
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $DataRoot 'runtime\install-state.json') -Encoding UTF8

if ($EnableAutoStart) {
    $arguments = @('autostart', 'enable', '--data-root', $DataRoot)
    if ($StartupDirectory) { $arguments += @('--startup-directory', [System.IO.Path]::GetFullPath($StartupDirectory)) }
    & (Join-Path $InstallRoot 'ChannelAgent.exe') @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Auto-start configuration failed.' }
}

Write-Output "install_root=$InstallRoot"
Write-Output "data_root=$DataRoot"
Write-Output "version=$($manifest.version)"
