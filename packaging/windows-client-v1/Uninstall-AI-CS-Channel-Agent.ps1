[CmdletBinding()]
param(
    [string]$InstallRoot,
    [string]$DataRoot,
    [string]$StartupDirectory,
    [switch]$RemoveData
)

$ErrorActionPreference = 'Stop'
if (-not $InstallRoot) { $InstallRoot = Join-Path $env:LOCALAPPDATA 'Programs\AI-CS\ChannelAgent' }
if (-not $DataRoot) { $DataRoot = Join-Path $env:LOCALAPPDATA 'AI-CS\ChannelAgent' }
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
$DataRoot = [System.IO.Path]::GetFullPath($DataRoot)

function Assert-SafeRemovalTarget([string]$Path) {
    $root = [System.IO.Path]::GetPathRoot($Path)
    if ($Path -eq $root -or $Path.Length -lt ($root.Length + 8)) {
        throw "Refusing unsafe removal target: $Path"
    }
}

Assert-SafeRemovalTarget $InstallRoot
Assert-SafeRemovalTarget $DataRoot
$executable = Join-Path $InstallRoot 'ChannelAgent.exe'
if (Test-Path -LiteralPath $executable -PathType Leaf) {
    & $executable stop --data-root $DataRoot --wait-seconds 3 | Out-Null
    $arguments = @('autostart', 'disable', '--data-root', $DataRoot)
    if ($StartupDirectory) { $arguments += @('--startup-directory', [System.IO.Path]::GetFullPath($StartupDirectory)) }
    & $executable @arguments | Out-Null
}
if (Test-Path -LiteralPath $InstallRoot) {
    Remove-Item -LiteralPath $InstallRoot -Recurse -Force
}
if ($RemoveData -and (Test-Path -LiteralPath $DataRoot)) {
    Remove-Item -LiteralPath $DataRoot -Recurse -Force
}
Write-Output "uninstalled=$InstallRoot"
Write-Output "data_preserved=$(-not $RemoveData)"
