[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [int]$Port,
    [Parameter(Mandatory = $true)]
    [ValidateSet('host', 'platform')]
    [string]$Kind
)

$ErrorActionPreference = 'Stop'
$listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
    Select-Object -First 1
if (-not $listener) {
    [pscustomobject]@{ stopped = $false; port = $Port; reason = 'NOT_LISTENING' } |
        ConvertTo-Json -Compress
    exit 0
}
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction Stop
$marker = if ($Kind -eq 'host') { 'run_channel_engine_production_host\.py' } else { 'uvicorn\s+app\.main:app' }
if ([string]$process.CommandLine -notmatch $marker) {
    throw "RC5_SHADOW_PROCESS_IDENTITY_MISMATCH:${Port}:$($process.ProcessId)"
}
Stop-Process -Id ([int]$process.ProcessId) -Force -ErrorAction Stop
foreach ($attempt in 1..40) {
    if (-not (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 100
}
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "RC5_SHADOW_PROCESS_DID_NOT_STOP:$Port"
}
[pscustomobject]@{ stopped = $true; port = $Port; pid = $process.ProcessId; kind = $Kind } |
    ConvertTo-Json -Compress
