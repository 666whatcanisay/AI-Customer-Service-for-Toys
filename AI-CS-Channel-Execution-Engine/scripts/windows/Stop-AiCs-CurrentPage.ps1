[CmdletBinding()]
param([string]$AiCsRoot)

$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
. (Join-Path $PSScriptRoot 'Resolve-AiCsRepositoryRoot.ps1')
$aiCsRoot = Resolve-AiCsRepositoryRoot $repoRoot $AiCsRoot
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$manager = Join-Path $repoRoot 'scripts\manage_current_page_auto_production.py'
$configCandidates = @(
    (Join-Path $aiCsRoot '.runtime\phase-e\config\green-standard.local.ps1'),
    (Join-Path $aiCsRoot '.runtime\r027-ux-acceptance-data-v1\ux-acceptance.local.ps1'),
    (Join-Path $aiCsRoot 'scripts\windows\config.local.ps1')
)
$config = $configCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
$dataRoot = Join-Path $env:LOCALAPPDATA 'AI-CS\ChannelAgent'
$installRoot = Join-Path $env:LOCALAPPDATA 'Programs\AI-CS\ChannelAgent'

if (Test-Path -LiteralPath $python -PathType Leaf) {
    & $python $manager stop | Out-Host
}

# Remove supervisors left by older builds before the single-instance lock existed.
$exactScripts = @(
    (Join-Path $repoRoot 'scripts\run_current_page_auto_production.py'),
    (Join-Path $repoRoot 'scripts\run_channel_agent_assistant_bridge.py'),
    (Join-Path $repoRoot 'scripts\run_controlled_pdd_reply_pilot.py'),
    (Join-Path $repoRoot 'scripts\run_channel_engine_production_host.py')
)
$processes = @(Get-CimInstance Win32_Process | Where-Object {
    $commandLine = [string]$_.CommandLine
    $matched = $false
    foreach ($script in $exactScripts) {
        if ($commandLine.IndexOf($script, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            $matched = $true
            break
        }
    }
    $matched
})
foreach ($process in $processes) {
    Stop-Process -Id ([int]$process.ProcessId) -Force -ErrorAction SilentlyContinue
}

$stopAiCs = Join-Path $aiCsRoot 'scripts\windows\stop_ai_customer_service.ps1'
if (
    (Test-Path -LiteralPath $stopAiCs -PathType Leaf) -and
    $config -and (Test-Path -LiteralPath $config -PathType Leaf)
) {
    & $stopAiCs -ConfigPath $config
}

Get-CimInstance Win32_Process | Where-Object {
    $path = [string]$_.ExecutablePath
    $commandLine = [string]$_.CommandLine
    $path.StartsWith($installRoot, [StringComparison]::OrdinalIgnoreCase) -or
    $commandLine.IndexOf($installRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or
    $commandLine.IndexOf($dataRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0
} | ForEach-Object {
    Stop-Process -Id ([int]$_.ProcessId) -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 2
$ports = @(60801, 8420, 8421, 8422, 8423, 8430, 18443)
$remaining = @(
    foreach ($port in $ports) {
        $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
        if ($listeners.Count -gt 0) { "${port}:$($listeners.OwningProcess -join ',')" }
    }
)
if ($remaining.Count -gt 0) {
    throw "Project ports are still listening: $($remaining -join '; ')"
}

Write-Host ''
Write-Host 'All AI-CS project components are stopped.' -ForegroundColor Green
