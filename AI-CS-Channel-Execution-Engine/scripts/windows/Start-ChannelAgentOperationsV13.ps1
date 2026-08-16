[CmdletBinding()]
param([int]$Port = 18020)

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$runtimeRoot = Join-Path $repoRoot '.runtime\channel-agent-lan-host'
$logRoot = Join-Path $runtimeRoot 'logs'

if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "PORT_${Port}_ALREADY_IN_USE"
}
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$env:PYTHONPATH = Join-Path $repoRoot 'src'
$env:CHANNEL_ENGINE_OPERATIONS_DATABASE_URL = 'sqlite:///' + ((Join-Path $runtimeRoot 'operations-console.sqlite3').Replace('\','/'))
$env:CHANNEL_ENGINE_AI_CS_ADMIN_URL = 'http://127.0.0.1:8422'

$process = Start-Process -FilePath $python -ArgumentList @(
    (Join-Path $repoRoot 'scripts\run_channel_engine_operations_console.py'),
    '--host', '127.0.0.1', '--port', [string]$Port
) -WorkingDirectory $repoRoot -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logRoot 'operations.stdout.log') `
    -RedirectStandardError (Join-Path $logRoot 'operations.stderr.log') `
    -PassThru

$ready = $false
foreach ($attempt in 1..40) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
        if ($health.status -eq 'healthy') {
            $ready = $true
            break
        }
    } catch {
        Start-Sleep -Milliseconds 250
    }
}
if (-not $ready) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    throw "OPERATIONS_CONSOLE_NOT_READY:$(Join-Path $logRoot 'operations.stderr.log')"
}
[pscustomobject]@{
    pid = $process.Id
    url = "http://127.0.0.1:$Port/ops/console#devices"
    profile = 'OPERATIONS_CONSOLE'
} | ConvertTo-Json -Compress
