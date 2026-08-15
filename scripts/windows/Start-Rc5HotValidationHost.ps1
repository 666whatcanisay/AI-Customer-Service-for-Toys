[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$EvidenceRoot,
    [Parameter(Mandatory = $true)]
    [string]$GatewayKeyReference,
    [int]$Port = 18443,
    [string]$DatabasePath,
    [string]$DatabaseEnvironmentId = 'RC5_CHANNEL_ENGINE_LOCAL',
    [string]$OfflineRuntimeRoot,
    [string]$GatewayBaseUrl = 'http://127.0.0.1:8420',
    [string]$DeviceCredentialIndex,
    [string]$AgentSpoolPath,
    [string]$CatalogStoreId,
    [string]$CatalogTenantId
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
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$repoGitSha = [string](& git -C $repoRoot rev-parse HEAD 2>$null | Select-Object -Last 1)
if ($LASTEXITCODE -ne 0 -or $repoGitSha -notmatch '^[0-9a-fA-F]{40}$') { throw 'RC5_VALIDATION_SOURCE_IDENTITY_UNAVAILABLE' }
$repoGitSha = $repoGitSha.Trim().ToLowerInvariant()
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
$agentSpoolPath = if ($AgentSpoolPath) {
    [System.IO.Path]::GetFullPath($AgentSpoolPath)
} elseif (-not [string]::IsNullOrWhiteSpace([string]$env:LOCALAPPDATA)) {
    Join-Path $env:LOCALAPPDATA 'AI-CS\ChannelAgent\runtime\observe-only-spool.sqlite3'
} else {
    ''
}

if ($null -ne (Get-Rc5LoopbackListenerPid $Port)) {
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
$env:CHANNEL_ENGINE_DATABASE_BINDING_PATH = "$databasePath.binding.json"
$env:CHANNEL_ENGINE_DATABASE_ENVIRONMENT_ID = $DatabaseEnvironmentId
$env:CHANNEL_ENGINE_REQUIRE_DATABASE_IDENTITY = 'true'
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
$env:CHANNEL_ENGINE_GATEWAY_TIMEOUT_SECONDS = '18'
$env:CHANNEL_ENGINE_AUTO_POLICY_MODE = 'AUTO_ALL_MESSAGES_V1'
if ([bool]$CatalogStoreId -ne [bool]$CatalogTenantId) {
    throw 'CatalogStoreId and CatalogTenantId must be configured together.'
}
if ($CatalogStoreId) {
    $env:CHANNEL_ENGINE_CATALOG_STORE_ID = $CatalogStoreId.Trim()
    $env:CHANNEL_ENGINE_CATALOG_TENANT_ID = $CatalogTenantId.Trim()
} else {
    Remove-Item Env:\CHANNEL_ENGINE_CATALOG_STORE_ID -ErrorAction SilentlyContinue
    Remove-Item Env:\CHANNEL_ENGINE_CATALOG_TENANT_ID -ErrorAction SilentlyContinue
}

$process = Start-Process -FilePath $python -ArgumentList @(
    (Join-Path $repoRoot 'scripts\run_channel_engine_production_host.py'),
    '--host', '127.0.0.1', '--port', [string]$Port
) -WorkingDirectory $repoRoot -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $evidenceRoot 'host.stdout.log') `
    -RedirectStandardError (Join-Path $evidenceRoot 'host.stderr.log') `
    -PassThru

$ready = $false
foreach ($attempt in 1..80) {
    try {
        $healthText = & curl.exe -ks --max-time 2 "https://127.0.0.1:$Port/health"
        if ($LASTEXITCODE -ne 0) { throw 'health probe failed' }
        $health = $healthText | ConvertFrom-Json
        if ($health.status -eq 'healthy' -and $health.service -eq 'channel-engine-host-control') {
            $ready = $true
            break
        }
    } catch {
        Start-Sleep -Milliseconds 250
    }
}
if (-not $ready) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    throw "RC5_VALIDATION_HOST_NOT_READY:$(Join-Path $evidenceRoot 'host.stderr.log')"
}

$listenerPid = Get-Rc5LoopbackListenerPid $Port
if ($null -eq $listenerPid) { throw "RC5_VALIDATION_HOST_LISTENER_MISSING:$Port" }
try {
$listenerProcess = Get-Process -Id $listenerPid -ErrorAction Stop
$bindingPath = "$databasePath.binding.json"
if (-not (Test-Path -LiteralPath $bindingPath -PathType Leaf)) {
    throw "RC5_RUNTIME_DATABASE_BINDING_MISSING:$bindingPath"
}
$binding = Get-Content -LiteralPath $bindingPath -Raw -Encoding UTF8 | ConvertFrom-Json
$governanceRoot = Join-Path $evidenceRoot 'rc5-pilot-governance'
$activationRoot = Join-Path $governanceRoot 'activations'
New-Item -ItemType Directory -Path $governanceRoot,$activationRoot -Force | Out-Null
$configSnapshotPath = Join-Path $governanceRoot 'channel-engine-host.config.json'
$configSnapshot = [ordered]@{
    schema = 'rc5-runtime-config-snapshot.v1'
    database_path = $databasePath
    offline_runtime_root = $offlineRuntimeRoot
    bind_address = '127.0.0.1'
    port = $Port
    observation_stage = $env:CHANNEL_ENGINE_OBSERVATION_STAGE
    gateway_base_url = $env:CHANNEL_ENGINE_GATEWAY_BASE_URL
    gateway_environment = $env:CHANNEL_ENGINE_GATEWAY_ENVIRONMENT
    auto_policy_mode = $env:CHANNEL_ENGINE_AUTO_POLICY_MODE
    catalog_store_id = if ($CatalogStoreId) { $env:CHANNEL_ENGINE_CATALOG_STORE_ID } else { $null }
    catalog_tenant_id = if ($CatalogTenantId) { $env:CHANNEL_ENGINE_CATALOG_TENANT_ID } else { $null }
    gateway_key_reference_sha256 = if (Test-Path -LiteralPath $GatewayKeyReference -PathType Leaf) { (Get-FileHash -LiteralPath $GatewayKeyReference -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null }
    real_send_enabled = $false
}
$configTemporary = "$configSnapshotPath.$([Guid]::NewGuid().ToString('N')).tmp"
try {
    $configSnapshot | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $configTemporary -Encoding UTF8
    Move-Item -LiteralPath $configTemporary -Destination $configSnapshotPath -Force
} finally {
    Remove-Item -LiteralPath $configTemporary -Force -ErrorAction SilentlyContinue
}
$configSha = (Get-FileHash -LiteralPath $configSnapshotPath -Algorithm SHA256).Hash.ToLowerInvariant()
$bindingSha = (Get-FileHash -LiteralPath $bindingPath -Algorithm SHA256).Hash.ToLowerInvariant()
$activationMaterial = "channel-engine-host|$listenerPid|$($listenerProcess.StartTime.ToUniversalTime().ToString('o'))|$configSha|$($binding.database_instance_id)"
$sha = [Security.Cryptography.SHA256]::Create()
try {
    $activationId = 'activation:' + ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($activationMaterial))).Replace('-','').ToLowerInvariant())
} finally {
    $sha.Dispose()
}
$activationPath = Join-Path $activationRoot 'channel-engine-host.json'
$activation = [ordered]@{
    schema = 'rc5-runtime-activation.v1'
    activation_id = $activationId
    component = 'CHANNEL_ENGINE_HOST'
    pid = [int]$listenerPid
    executable_path = [IO.Path]::GetFullPath([string]$listenerProcess.Path)
    manifest_created_at = [DateTime]::UtcNow.ToString('o')
    service_started_at = $process.StartTime.ToUniversalTime().ToString('o')
    process_started_at = $listenerProcess.StartTime.ToUniversalTime().ToString('o')
    config_source_path = [IO.Path]::GetFullPath($configSnapshotPath)
    config_sha256 = $configSha
    source_repository_path = $repoRoot
    source_revision = $repoGitSha
    canonical_database_path = [IO.Path]::GetFullPath($databasePath)
    binding_sidecar_path = [IO.Path]::GetFullPath($bindingPath)
    database_instance_id = [string]$binding.database_instance_id
    environment_id = [string]$binding.environment_id
    database_role = [string]$binding.database_role
    revision = [string]$binding.runtime_storage_version
    binding_sidecar_sha256 = $bindingSha
    ports = @([int]$Port)
    runtime_data_paths = [ordered]@{
        HOST_CONTROL = [IO.Path]::GetFullPath($databasePath)
        CONVERSATION_BUFFER = [IO.Path]::GetFullPath((Join-Path $offlineRuntimeRoot 'conversation-buffer.sqlite3'))
        OFFLINE_CONTROL = [IO.Path]::GetFullPath((Join-Path $offlineRuntimeRoot 'offline-control.sqlite3'))
        AGENT_SPOOL = $agentSpoolPath
    }
    safety_flags = [ordered]@{ real_send_enabled = $false }
}
$activationTemporary = "$activationPath.$([Guid]::NewGuid().ToString('N')).tmp"
try {
    $activation | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $activationTemporary -Encoding UTF8
    Move-Item -LiteralPath $activationTemporary -Destination $activationPath -Force
} finally {
    Remove-Item -LiteralPath $activationTemporary -Force -ErrorAction SilentlyContinue
}
[pscustomobject]@{
    host_pid = $listenerPid
    launcher_pid = $process.Id
    observation_stage = $env:CHANNEL_ENGINE_OBSERVATION_STAGE
    offline_runtime_root = $env:CHANNEL_ENGINE_OFFLINE_RUNTIME_ROOT
    database_path = $databasePath
    gateway_base_url = $env:CHANNEL_ENGINE_GATEWAY_BASE_URL
    runtime_activation = $activationPath
    real_send_enabled = $false
} | ConvertTo-Json -Depth 3 -Compress
} catch {
    Stop-Process -Id $listenerPid -Force -ErrorAction SilentlyContinue
    throw
}
