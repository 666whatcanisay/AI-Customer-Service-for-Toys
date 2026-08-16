[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [int]$Port,
    [Parameter(Mandatory = $true)]
    [ValidateSet('host', 'platform')]
    [string]$Kind
)

$ErrorActionPreference = 'Stop'
function Get-Rc5LoopbackListenerPid([int]$ListenerPort) {
    $matches = @(
        netstat -ano -p TCP |
            Select-String "^\s*TCP\s+(127\.0\.0\.1|\[::1\]):$ListenerPort\s+\S+\s+LISTENING\s+(\d+)\s*$" |
            ForEach-Object { [int]$_.Matches[0].Groups[2].Value } |
            Sort-Object -Unique
    )
    if ($matches.Count -gt 1) { throw "PORT_${ListenerPort}_MULTIPLE_LISTENERS" }
    if ($matches.Count -eq 1) { return [int]$matches[0] }
    return $null
}
$processId = Get-Rc5LoopbackListenerPid $Port
if ($null -eq $processId) {
    [pscustomobject]@{ stopped = $false; port = $Port; reason = 'NOT_LISTENING' } |
        ConvertTo-Json -Compress
    exit 0
}
$marker = if ($Kind -eq 'host') { 'run_channel_engine_production_host\.py' } else { 'uvicorn\s+app\.main:app' }
$identityConfirmed = $false
try {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction Stop
    $identityConfirmed = [string]$process.CommandLine -match $marker
} catch {
    # Win32_Process can fail under low page-file pressure.  The exact loopback
    # listener and service-specific health identity remain a fail-closed
    # fallback; no unrelated process is stopped on a generic 200 response.
    try {
        $health = if ($Kind -eq 'host') {
            $healthText = & curl.exe -ks --max-time 2 "https://127.0.0.1:$Port/health"
            if ($LASTEXITCODE -ne 0) { throw 'health probe failed' }
            $healthText | ConvertFrom-Json
        } else {
            Invoke-RestMethod -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
        }
        $expectedService = if ($Kind -eq 'host') { 'channel-engine-host-control' } else { 'platform-backend' }
        $identityConfirmed = [string]$health.service -eq $expectedService
    } catch {
        $identityConfirmed = $false
    }
}
if (-not $identityConfirmed) {
    throw "RC5_SHADOW_PROCESS_IDENTITY_MISMATCH:${Port}:$processId"
}
Stop-Process -Id $processId -Force -ErrorAction Stop
foreach ($attempt in 1..40) {
    if ($null -eq (Get-Rc5LoopbackListenerPid $Port)) { break }
    Start-Sleep -Milliseconds 100
}
if ($null -ne (Get-Rc5LoopbackListenerPid $Port)) {
    throw "RC5_SHADOW_PROCESS_DID_NOT_STOP:$Port"
}
[pscustomobject]@{ stopped = $true; port = $Port; pid = $processId; kind = $Kind } |
    ConvertTo-Json -Compress
