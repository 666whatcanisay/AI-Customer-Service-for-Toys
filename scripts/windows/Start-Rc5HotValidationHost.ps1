[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$EvidenceRoot,
    [Parameter(Mandatory = $true)]
    [string]$GatewayKeyReference,
    [int]$Port = 18443,
    [string]$DatabasePath,
    [string]$OfflineRuntimeRoot,
    [string]$GatewayBaseUrl = 'http://127.0.0.1:8420',
    [string]$DeviceCredentialIndex
)

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$runtimeRoot = Join-Path $repoRoot '.runtime\channel-agent-lan-host'
$certificate = Join-Path $runtimeRoot 'tls\channel-agent-host-v2.pem'
$privateKey = Join-Path $runtimeRoot 'tls\channel-agent-host-key.encrypted.pem'
$evidenceRoot = [System.IO.Path]::GetFullPath($EvidenceRoot)
$databasePath = if ($DatabasePath) {
    [System.IO.Path]::GetFullPath($DatabasePath)
} else {
    Join-Path $repoRoot '.runtime\channel-engine.sqlite3'
}
$offlineRuntimeRoot = if ($OfflineRuntimeRoot) {
    [System.IO.Path]::GetFullPath($OfflineRuntimeRoot)
} else {
    Join-Path $evidenceRoot 'host-offline-runtime'
}
$deviceCredentialIndex = if ($DeviceCredentialIndex) {
    [System.IO.Path]::GetFullPath($DeviceCredentialIndex)
} else {
    Join-Path $runtimeRoot 'device-credential-index.json'
}

if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "PORT_${Port}_ALREADY_IN_USE"
}
foreach ($required in @($python, $certificate, $privateKey, $GatewayKeyReference, $deviceCredentialIndex)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "RC5_VALIDATION_DEPENDENCY_MISSING:$required"
    }
}
New-Item -ItemType Directory -Path $evidenceRoot -Force | Out-Null

$env:PYTHONPATH = Join-Path $repoRoot 'src'
$env:CHANNEL_ENGINE_DATABASE_URL = 'sqlite:///' + ($databasePath.Replace('\','/'))
$env:CHANNEL_ENGINE_AGENT_CONTROL_V2_ENABLED = 'true'
$env:CHANNEL_ENGINE_AGENT_HOST_ID = 'ai-cs-desktop-0345200'
$env:CHANNEL_ENGINE_AGENT_PUBLIC_URL = "https://127.0.0.1:$Port"
$env:CHANNEL_ENGINE_AGENT_PAIRING_CREDENTIAL_REFERENCE = 'wincred://AI-CS/ChannelEngine/ai-cs-desktop-0345200/PairingCodeV2'
Remove-Item Env:\CHANNEL_ENGINE_AGENT_PAIRING_CODE -ErrorAction SilentlyContinue
$env:CHANNEL_ENGINE_AGENT_CA_CERTIFICATE = $certificate
$env:CHANNEL_ENGINE_DEVICE_CREDENTIAL_INDEX = $deviceCredentialIndex
$env:CHANNEL_ENGINE_AGENT_ENVIRONMENT = 'STAGING'
$env:CHANNEL_ENGINE_TLS_CERTIFICATE = $certificate
$env:CHANNEL_ENGINE_TLS_PRIVATE_KEY = $privateKey
$env:CHANNEL_ENGINE_TLS_PRIVATE_KEY_CREDENTIAL_REFERENCE = 'wincred://AI-CS/ChannelEngine/ai-cs-desktop-0345200/TLSKeyPassword'
$env:CHANNEL_ENGINE_AI_CS_SERVICE_CONTROL_ENABLED = 'true'
$env:CHANNEL_ENGINE_AI_CS_SERVICE_ID = 'ai-cs-platform'
$env:CHANNEL_ENGINE_AI_CS_SERVICE_KEY_ID = 'service-key-v1'
$env:CHANNEL_ENGINE_AI_CS_SERVICE_CREDENTIAL_REFERENCE = 'wincred://AI-CS/ChannelEngine/ai-cs-desktop-0345200/AI-CSService'
$env:CHANNEL_ENGINE_OBSERVATION_STAGE = 'AI_SUGGESTIONS'
$env:CHANNEL_ENGINE_OFFLINE_RUNTIME_ROOT = $offlineRuntimeRoot
$env:CHANNEL_ENGINE_BUFFER_QUIET_WINDOW_MS = '500'
$env:CHANNEL_ENGINE_GATEWAY_KEY_REFERENCE = $GatewayKeyReference
$env:CHANNEL_ENGINE_GATEWAY_BASE_URL = $GatewayBaseUrl.TrimEnd('/')
$env:CHANNEL_ENGINE_GATEWAY_ENVIRONMENT = 'mock'
$env:CHANNEL_ENGINE_GATEWAY_CLIENT_ID = 'channel-engine'
$env:CHANNEL_ENGINE_GATEWAY_KEY_ID = 'gateway-key-v1'
$env:CHANNEL_ENGINE_GATEWAY_TIMEOUT_SECONDS = '30'

$process = Start-Process -FilePath $python -ArgumentList @(
    (Join-Path $repoRoot 'scripts\run_channel_engine_production_host.py'),
    '--host', '127.0.0.1', '--port', [string]$Port
) -WorkingDirectory $repoRoot -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $evidenceRoot 'host.stdout.log') `
    -RedirectStandardError (Join-Path $evidenceRoot 'host.stderr.log') `
    -PassThru

$ready = $false
foreach ($attempt in 1..80) {
    & $python -c "import httpx,sys; r=httpx.get(sys.argv[1],verify=False,timeout=2,trust_env=False); raise SystemExit(0 if r.status_code == 200 and r.json().get('status') == 'healthy' else 1)" "https://127.0.0.1:$Port/health" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $ready = $true
        break
    }
    Start-Sleep -Milliseconds 250
}
if (-not $ready) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    throw "RC5_VALIDATION_HOST_NOT_READY:$(Join-Path $evidenceRoot 'host.stderr.log')"
}

$owner = Get-NetTCPConnection -State Listen -LocalPort $Port | Select-Object -First 1
[pscustomobject]@{
    host_pid = $owner.OwningProcess
    launcher_pid = $process.Id
    observation_stage = $env:CHANNEL_ENGINE_OBSERVATION_STAGE
    offline_runtime_root = $env:CHANNEL_ENGINE_OFFLINE_RUNTIME_ROOT
    database_path = $databasePath
    gateway_base_url = $env:CHANNEL_ENGINE_GATEWAY_BASE_URL
    real_send_enabled = $false
} | ConvertTo-Json -Depth 3 -Compress
