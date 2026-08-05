$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$scriptsRoot = Join-Path $repositoryRoot 'scripts\windows'
. (Join-Path $scriptsRoot 'common_ai_customer_service.ps1')

foreach ($name in @(
    'start_ai_customer_service.ps1',
    'status_ai_customer_service.ps1',
    'stop_ai_customer_service.ps1',
    'start_ai_cs_server.ps1',
    'status_ai_cs_server.ps1',
    'stop_ai_cs_server.ps1',
    'start_ai_cs_server.bat'
)) {
    if (-not (Test-Path -LiteralPath (Join-Path $scriptsRoot $name) -PathType Leaf)) {
        throw "Required lifecycle entry is missing: $name"
    }
}

$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) "ops-gateway-runtime-$([Guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Force -Path $temporaryRoot | Out-Null
try {
    $secretPath = Join-Path $temporaryRoot 'gateway-hmac.secret'
    [IO.File]::WriteAllText($secretPath, ('s' * 32) + "`n", [Text.UTF8Encoding]::new($false))
    $config = @{
        RepositoryRoot = $repositoryRoot
        RuntimeMode = 'standard'
        BindAddress = '127.0.0.1'
        RagPort = 18000
        CorsAllowedOrigins = @('http://127.0.0.1:5173')
        OllamaModel = 'model'
        OllamaBaseUrl = 'http://127.0.0.1:11434'
        PlatformPort = 18011
        RagKnowledgeBasePath = (Join-Path $temporaryRoot 'knowledge')
        RagVectorDbPath = (Join-Path $temporaryRoot 'vectors')
        RagLogDirectory = (Join-Path $temporaryRoot 'logs')
        RagPrimaryCollectionName = 'documents'
        RagActiveCollectionName = 'active'
        GatewayEnabled = $true
        GatewayClientId = 'channel-engine'
        GatewayKeyId = 'gateway-key-v1'
        GatewaySecretReference = $secretPath
        GatewayStatePath = (Join-Path $temporaryRoot 'gateway-state.sqlite3')
        GatewayClockSkewSeconds = 300
        GatewayNonceTtlSeconds = 600
        GatewayDecisionRetentionSeconds = 604800
        GatewayDecisionLeaseSeconds = 30
    }
    $runtimeEnvironment = Get-RagRuntimeEnvironment $config 'http://127.0.0.1:5173'
    if ($runtimeEnvironment.GATEWAY_ENABLED -ne 'true') { throw 'Gateway enablement was not propagated.' }
    if ($runtimeEnvironment.GATEWAY_HMAC_SECRET_FILE -ne $secretPath) { throw 'Gateway secret reference was not propagated.' }
    if ($runtimeEnvironment.ContainsKey('GATEWAY_HMAC_SECRET')) { throw 'Plaintext Gateway secret must never enter unified runtime config.' }
    if ($runtimeEnvironment.AI_CS_SERVER_RUNTIME_MODE -ne 'standard') { throw 'Runtime mode was not propagated.' }
    Assert-AiCsGatewayProductionConfig $config | Out-Null

    # The formal secret reference lives below the ignored .runtime tree. This
    # must work in Windows PowerShell 5.1, which lacks Path.GetRelativePath.
    $repositorySecretRoot = Join-Path $repositoryRoot ".runtime\ops-gateway-runtime-$([Guid]::NewGuid().ToString('N'))"
    $repositorySecretPath = Join-Path $repositorySecretRoot 'gateway-hmac.secret'
    New-Item -ItemType Directory -Force -Path $repositorySecretRoot | Out-Null
    try {
        [IO.File]::WriteAllText($repositorySecretPath, ('r' * 32), [Text.UTF8Encoding]::new($false))
        $config.GatewaySecretReference = $repositorySecretPath
        Assert-AiCsGatewayProductionConfig $config | Out-Null
    } finally {
        $config.GatewaySecretReference = $secretPath
        Remove-Item -LiteralPath $repositorySecretRoot -Recurse -Force -ErrorAction SilentlyContinue
    }

    $headers = New-AiCsGatewayAuthHeaders $config 'GET' '/gateway/v1/health'
    foreach ($header in @('Authorization','X-AI-CS-Contract-Version','X-AI-CS-Timestamp','X-AI-CS-Nonce','X-AI-CS-Content-SHA256','X-Request-ID','X-Correlation-ID','Idempotency-Key')) {
        if ([string]::IsNullOrWhiteSpace([string]$headers[$header])) { throw "Missing signed health header: $header" }
    }
    if ([string]$headers.Authorization -match ('s' * 16)) { throw 'Gateway secret leaked into Authorization metadata.' }

    [IO.File]::WriteAllText($secretPath, '0123456789abcdef0123456789abcdef', [Text.UTF8Encoding]::new($false))
    $config.GatewayClientId = 'agent-01'
    $config.GatewayKeyId = 'key-01'
    $vectorBody = [Text.Encoding]::UTF8.GetBytes('{"contract_version":"1.0"}')
    $vectorHeaders = New-AiCsGatewayAuthHeaders $config 'POST' '/gateway/v1/decisions' $vectorBody `
        -Timestamp '2026-08-05T00:00:00Z' `
        -Nonce 'bm9uY2UtZm9yLXRlc3QtMDAx' `
        -RequestId 'req-001' `
        -CorrelationId 'corr-001' `
        -IdempotencyKey 'idem-001'
    if ($vectorHeaders.'X-AI-CS-Content-SHA256' -ne '84786626e94027a1c329b242d5c4c35eb285e80bd77cebb15c81fdb729c03227') {
        throw 'PowerShell Gateway content hash does not match frozen Contract V1.'
    }
    if ($vectorHeaders.Authorization -ne 'HMAC-SHA256 Credential=agent-01/key-01,Signature=FYWXv1salDMEWFLncJVmokCssvS0fdTEbhyxOAuC9uc') {
        throw 'PowerShell Gateway signature does not match frozen Contract V1.'
    }

    $fixtureRoot = Join-Path $temporaryRoot 'wrapper-fixture'
    New-Item -ItemType Directory -Force -Path $fixtureRoot | Out-Null
    foreach ($name in @('start_ai_cs_server.ps1','status_ai_cs_server.ps1','stop_ai_cs_server.ps1')) {
        Copy-Item -LiteralPath (Join-Path $scriptsRoot $name) -Destination (Join-Path $fixtureRoot $name)
    }
    @'
function Resolve-AiCustomerServiceConfigPath([string]$ConfigPath) { return $ConfigPath }
function Get-LocalConfig([string]$ConfigPath) { return @{ AdminWebUrl='http://127.0.0.1:5174/' } }
function Assert-AiCsGatewayProductionConfig($Config) { return $true }
function Wait-AiCsGatewayRuntimeReady($Config, [int]$Seconds) { return [pscustomobject]@{ status='HEALTHY'; version='ai-cs-gateway.v1'; contract_version='1.0' } }
function Get-AiCsGatewayRuntimeHealth($Config) { return [pscustomobject]@{ status='HEALTHY'; version='ai-cs-gateway.v1'; contract_version='1.0' } }
function Get-AiCsServerRuntimeConsole($Config) { return [pscustomobject]@{ server=[pscustomobject]@{ status='READY'; version='ai-cs-server-runtime.rc1'; runtime_mode='standard' }; gateway=[pscustomobject]@{ configuration_state='CONFIGURED' } } }
'@ | Set-Content -LiteralPath (Join-Path $fixtureRoot 'common_ai_customer_service.ps1') -Encoding UTF8
    @'
param([string]$ConfigPath,[switch]$NoBrowser,[string]$Mode)
"start|$ConfigPath|$NoBrowser|$Mode" | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'start.marker')
'@ | Set-Content -LiteralPath (Join-Path $fixtureRoot 'start_ai_customer_service.ps1') -Encoding UTF8
    @'
param([string]$ConfigPath,[string]$Mode)
"status|$ConfigPath|$Mode" | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'status.marker')
'@ | Set-Content -LiteralPath (Join-Path $fixtureRoot 'status_ai_customer_service.ps1') -Encoding UTF8
    @'
param([string]$ConfigPath)
"stop|$ConfigPath" | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'stop.marker')
'@ | Set-Content -LiteralPath (Join-Path $fixtureRoot 'stop_ai_customer_service.ps1') -Encoding UTF8

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $fixtureRoot 'start_ai_cs_server.ps1') -ConfigPath 'fixture.ps1' -NoBrowser -Mode Local -GatewayTimeoutSeconds 1 | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath (Join-Path $fixtureRoot 'start.marker'))) { throw 'Production start wrapper delegation failed.' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $fixtureRoot 'status_ai_cs_server.ps1') -ConfigPath 'fixture.ps1' -Mode Local | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath (Join-Path $fixtureRoot 'status.marker'))) { throw 'Production status wrapper delegation failed.' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $fixtureRoot 'stop_ai_cs_server.ps1') -ConfigPath 'fixture.ps1' | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath (Join-Path $fixtureRoot 'stop.marker'))) { throw 'Production stop wrapper delegation failed.' }

    Write-Host 'OPS Gateway Server Runtime lifecycle checks: PASS'
} finally {
    Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
}
