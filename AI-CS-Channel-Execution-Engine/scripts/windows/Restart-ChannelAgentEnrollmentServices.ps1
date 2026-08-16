[CmdletBinding()]
param(
    [string]$AiCsRoot,
    [int]$OperationsPort = 18020,
    [string]$HostControlUrl
)

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
. (Join-Path $PSScriptRoot 'Resolve-AiCsRepositoryRoot.ps1')
$AiCsRoot = Resolve-AiCsRepositoryRoot $repoRoot $AiCsRoot

$common = Join-Path $AiCsRoot 'scripts\windows\common_ai_customer_service.ps1'
$configPath = Join-Path $AiCsRoot '.runtime\r027-ux-acceptance-data-v1\ux-acceptance.local.ps1'
if (-not (Test-Path -LiteralPath $common -PathType Leaf)) { throw 'AI_CS_COMMON_SCRIPT_MISSING' }
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { throw 'AI_CS_RUNTIME_CONFIG_MISSING' }

. $common
$config = Get-LocalConfig $configPath
$platformCheck = Test-RecordedProcess $config 'platform'
$platformListener = Get-NetTCPConnection -State Listen -LocalPort ([int]$config.PlatformPort) -ErrorAction SilentlyContinue |
    Select-Object -First 1
# After a Windows reboot there is intentionally no live process to verify.
# Preserve strict identity verification whenever the platform port is occupied,
# but allow the managed launcher below to recreate a fully stopped service.
if ($platformListener -and -not $platformCheck.Valid) {
    throw "AI_CS_PLATFORM_IDENTITY_NOT_VERIFIED:$($platformCheck.Reason)"
}

$hostListener = Get-NetTCPConnection -State Listen -LocalPort 18443 -ErrorAction SilentlyContinue |
    Select-Object -First 1
if (-not $hostListener) { throw 'HOST_CONTROL_18443_NOT_RUNNING' }
$hostProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($hostListener.OwningProcess)" -ErrorAction Stop
if ([string]$hostProcess.CommandLine -notmatch 'run_channel_engine_production_host\.py') {
    throw 'HOST_CONTROL_18443_IDENTITY_NOT_VERIFIED'
}

$operationsListener = Get-NetTCPConnection -State Listen -LocalPort $OperationsPort -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($operationsListener) {
    $operationsProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($operationsListener.OwningProcess)" -ErrorAction Stop
    if ([string]$operationsProcess.CommandLine -notmatch 'run_channel_engine_operations_console\.py') {
        throw "OPERATIONS_${OperationsPort}_IDENTITY_NOT_VERIFIED"
    }
}

$hostId = 'ai-cs-' + (($env:COMPUTERNAME -replace '[^A-Za-z0-9._-]', '-').ToLowerInvariant())
$runtimeRoot = Join-Path $repoRoot '.runtime\channel-agent-lan-host'
if (-not $HostControlUrl) {
    $candidatePaths = @(
        (Join-Path $runtimeRoot 'lan-candidate.json'),
        (Join-Path $runtimeRoot 'lan-candidate-v13.json')
    ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }
    foreach ($candidatePath in $candidatePaths) {
        try {
            $candidate = Get-Content -LiteralPath $candidatePath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ([string]$candidate.server_url) {
                $HostControlUrl = [string]$candidate.server_url
                break
            }
        } catch {
            continue
        }
    }
}
if (-not $HostControlUrl) { $HostControlUrl = 'https://127.0.0.1:18443' }
$hostControlUri = $null
if (-not [Uri]::TryCreate($HostControlUrl, [UriKind]::Absolute, [ref]$hostControlUri) -or
    $hostControlUri.Scheme -ne 'https' -or $hostControlUri.Port -ne 18443) {
    throw 'HOST_CONTROL_URL_INVALID'
}
$env:CHANNEL_AGENT_INTEGRATION_ENABLED = 'true'
$env:CHANNEL_AGENT_SERVER_URL = $hostControlUri.AbsoluteUri.TrimEnd('/')
$env:CHANNEL_AGENT_SERVICE_ID = 'ai-cs-platform'
$env:CHANNEL_AGENT_SERVICE_KEY_ID = 'service-key-v1'
$env:CHANNEL_AGENT_SERVICE_CREDENTIAL_REFERENCE = "wincred://AI-CS/ChannelEngine/$hostId/AI-CSService"
$env:CHANNEL_AGENT_CA_CERTIFICATE_FILE = Join-Path $runtimeRoot 'tls\channel-agent-host-v2.pem'
$runtimeEnvironment = Get-LocalPlatformEnvironment $config

# Apply the additive AI-CS schema change before replacing the running platform.
# The migration is executed with the same managed environment as the service;
# a failure stops the rollout before the current process is touched.
Invoke-WithProcessEnvironment $runtimeEnvironment {
    Invoke-PlatformMigration $config
} | Out-Null

Stop-ManagedService $config 'platform'
$platform = Start-ManagedServiceWithEnvironment $config 'platform' $config.PlatformPythonPath @(
    '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port',
    [string]$config.PlatformPort, '--no-access-log'
) (Join-Path $AiCsRoot 'platform_backend') 'app.main:app' ([int]$config.PlatformPort) $runtimeEnvironment

$platformReady = $false
foreach ($attempt in 1..40) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$($config.PlatformPort)/health" -TimeoutSec 2
        if ($health.status -eq 'ok') { $platformReady = $true; break }
    } catch {
        Start-Sleep -Milliseconds 250
    }
}
if (-not $platformReady) {
    throw "AI_CS_PLATFORM_NOT_READY:$($config.PlatformPort)"
}

$openApi = Invoke-RestMethod -Uri "http://127.0.0.1:$($config.PlatformPort)/openapi.json" -TimeoutSec 5
$paths = @($openApi.paths.PSObject.Properties.Name)
if ('/api/v1/admin/desktop-workflow/devices/{agent_id}/enrollment-grants' -notin $paths) {
    throw 'AI_CS_ENROLLMENT_GRANT_ROUTE_MISSING'
}

if ($operationsListener) {
    $parentId = [int]$operationsProcess.ParentProcessId
    Stop-Process -Id ([int]$operationsListener.OwningProcess) -Force -ErrorAction Stop
    Start-Sleep -Milliseconds 250
    $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$parentId" -ErrorAction SilentlyContinue
    if ($parent -and [string]$parent.CommandLine -match 'run_channel_engine_operations_console\.py') {
        Stop-Process -Id $parentId -Force -ErrorAction SilentlyContinue
    }
}

$operationsResult = & (Join-Path $PSScriptRoot 'Start-ChannelAgentOperationsV13.ps1') -Port $OperationsPort
if ($LASTEXITCODE -ne 0) { throw 'OPERATIONS_CONSOLE_RESTART_FAILED' }
$operationsHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$OperationsPort/health" -TimeoutSec 5
if ($operationsHealth.status -ne 'healthy') { throw 'OPERATIONS_CONSOLE_NOT_HEALTHY' }

[pscustomobject]@{
    ai_cs_platform = 'HEALTHY'
    ai_cs_platform_pid = $platform.Id
    operations_console = 'HEALTHY'
    operations_port = $OperationsPort
    host_control = 'UNCHANGED'
    host_control_port = 18443
    pdd_browser = 'UNCHANGED'
    operations_start = $operationsResult
} | ConvertTo-Json -Depth 4 -Compress
