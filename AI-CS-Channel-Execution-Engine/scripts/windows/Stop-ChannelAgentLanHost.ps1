[CmdletBinding()]
param([string]$AiCsRoot)
$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if (-not $AiCsRoot) { $AiCsRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot '..\AI-CS')) }
$statePath = Join-Path $repoRoot '.runtime\channel-agent-lan-host\host-state.json'
if (Test-Path -LiteralPath $statePath -PathType Leaf) {
    $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($processId in @([int]$state.operations_pid, [int]$state.discovery_pid, [int]$state.engine_pid)) {
        if ($processId -le 0) { continue }
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
        if ($process -and [string]$process.CommandLine -like "*$repoRoot*") {
            Stop-Process -Id $processId -Force
        }
    }
    Remove-Item -LiteralPath $statePath -Force
}
$aiCsStop = Join-Path $AiCsRoot 'scripts\windows\stop_ai_customer_service.ps1'
if (Test-Path -LiteralPath $aiCsStop -PathType Leaf) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $aiCsStop
}
Write-Host 'Channel Agent 局域网主机已安全停止；设备绑定、Receipt 与审计记录未删除。' -ForegroundColor Green
