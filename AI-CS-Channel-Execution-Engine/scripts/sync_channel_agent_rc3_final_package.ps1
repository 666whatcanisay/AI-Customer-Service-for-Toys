[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$SourcePackageRoot,
    [string]$InstallRoot = (Join-Path $PSScriptRoot '..\dist\windows-client-v2\AI-CS-Channel-Agent'),
    [string]$DataRoot = (Join-Path $env:LOCALAPPDATA 'AI-CS\ChannelAgent')
)

$ErrorActionPreference = 'Stop'
$SourcePackageRoot = [IO.Path]::GetFullPath($SourcePackageRoot)
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
$DataRoot = [IO.Path]::GetFullPath($DataRoot)
$statePath = Join-Path $DataRoot 'runtime\channel-agent-state.json'
$before = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
$runtimePid = [int]$before.pid
$edgePid = [int]$(if ($before.browser_pid) { $before.browser_pid } else { 0 })
$exeTarget = Join-Path $InstallRoot 'ChannelAgent.exe'
$backupRoot = Join-Path $InstallRoot ('.rc3-upgrade-backups\final-package-sync-' + [DateTimeOffset]::UtcNow.ToString('yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$replaced = [System.Collections.Generic.List[string]]::new()

function Set-AtomicFile([string]$Source, [string]$Target) {
    $pending = "$Target.final-pending"
    $replaceBackup = "$Target.final-replace-backup"
    Copy-Item -LiteralPath $Source -Destination $pending -Force
    try {
        [IO.File]::Replace($pending, $Target, $replaceBackup, $true)
    }
    finally {
        if (Test-Path -LiteralPath $pending -PathType Leaf) { Remove-Item -LiteralPath $pending -Force }
        if (Test-Path -LiteralPath $replaceBackup -PathType Leaf) { Remove-Item -LiteralPath $replaceBackup -Force }
    }
}

try {
    Get-CimInstance Win32_Process -Filter "Name='ChannelAgent.exe'" | Where-Object {
        $_.ExecutablePath -and [IO.Path]::GetFullPath($_.ExecutablePath).Equals(
            $exeTarget, [StringComparison]::OrdinalIgnoreCase
        )
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

    foreach ($relative in @('ChannelAgent.exe', 'release-manifest.json', 'install\Upgrade-ChannelAgent-RC3.ps1')) {
        $source = Join-Path $SourcePackageRoot $relative
        $target = Join-Path $InstallRoot $relative
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing final package file: $relative" }
        $backup = Join-Path $backupRoot $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $backup) -Force | Out-Null
        Copy-Item -LiteralPath $target -Destination $backup -Force
        Set-AtomicFile $source $target
        $replaced.Add($relative)
    }

    cmd.exe /c start "" /b "$exeTarget"
    Start-Sleep -Seconds 5
    $after = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not (Get-Process -Id $runtimePid -ErrorAction SilentlyContinue)) { throw 'Runtime PID changed during final package sync.' }
    if ($edgePid -gt 0 -and -not (Get-Process -Id $edgePid -ErrorAction SilentlyContinue)) { throw 'Managed Edge PID changed during final package sync.' }
    foreach ($field in @('agent_id', 'device_id', 'identity_status', 'binding_revision', 'browser_profile_reference')) {
        if ([string]$after.$field -ne [string]$before.$field) { throw "Protected state changed: $field" }
    }
    [pscustomobject]@{
        status = 'PASSED'
        runtime_pid = $runtimePid
        edge_pid = $edgePid
        identity_status = $after.identity_status
        binding_revision = $after.binding_revision
        synchronized_files = @($replaced)
        backup_root = $backupRoot
    } | ConvertTo-Json -Depth 4
}
catch {
    foreach ($relative in $replaced) {
        $backup = Join-Path $backupRoot $relative
        if (Test-Path -LiteralPath $backup -PathType Leaf) {
            Set-AtomicFile $backup (Join-Path $InstallRoot $relative)
        }
    }
    cmd.exe /c start "" /b "$exeTarget"
    throw
}
